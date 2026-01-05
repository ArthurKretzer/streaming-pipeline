import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';
import { sleep } from 'k6';
import { Connection, SCHEMA_TYPE_AVRO, SCHEMA_TYPE_STRING, SchemaRegistry, Writer } from "k6/x/kafka";

// Load data and schema
const rawData = JSON.parse(open("./dataset/robot_data.json"));
let schemaContent = open("./schemas/schema.json");
// k6/JS uses float64 (double), so we need to adjust the schema
schemaContent = schemaContent.replace(/"type":\s*"float"/g, '"type": "double"');

const brokers = (__ENV.BROKERS || "172.16.208.242:31289").split(",");
const topic = "robot_data-avro";

const writer = new Writer({
    brokers: brokers,
    topic: topic,
    autoCreateTopic: false, // Topic creation handled in setup()
    balancer: "balancer_murmur2", // Ensure partition affinity based on key
    batchSize: 1,
    batchTimeout: 0, // Go defaults to 1s if 0 is provided, but batch size of 1 ignores it.
    requiredAcks: 1, // Leader ack. Use -1 for all ISR if desired.
});

const schemaRegistry = new SchemaRegistry({
    url: __ENV.SCHEMA_REGISTRY_URL || "http://172.16.208.242:32081",
});

const TEST_TYPE = __ENV.TEST_TYPE || 'smoke';

const SCENARIOS = {
    smoke: {
        executor: 'constant-arrival-rate',
        rate: 500,
        timeUnit: '1s',
        duration: '1m',
        preAllocatedVUs: 500,
        maxVUs: 1000,
    },
    stress: {
        // Push beyond average in steps: 1k -> 2k -> 5k -> 10k
        executor: 'ramping-arrival-rate',
        startRate: 1000,
        timeUnit: '1s',
        preAllocatedVUs: 400,
        maxVUs: 1200,
        stages: [
            { target: 8000, duration: '5m' }, // Scale-up
            { target: 8000, duration: '5m' }, // Steady 5x load
            { target: 0, duration: '5m' }, // Scale-down
        ],
    },
    breakpoint: {
        // Ramp up to find max sustainable rate
        executor: 'ramping-arrival-rate',
        startRate: 1000,
        timeUnit: '1s',
        preAllocatedVUs: 400,
        maxVUs: 1200,
        stages: [
            { target: 15000, duration: '15m' }, // Linear ramp to 10k to find breakpoint
        ],
    },
    spike: {
        executor: 'ramping-arrival-rate',
        startRate: 1000,
        timeUnit: '1s',
        preAllocatedVUs: 400,
        maxVUs: 1200,
        stages: [
            { target: 1000, duration: '1m' }, // Warm up
            { target: 8000, duration: '30s' }, // Spike to 5x load
            { target: 8000, duration: '1m' }, // Sustain spike
            { target: 4000, duration: '30s' }, // Scale down / Recovery
            { target: 4000, duration: '1m' }, // Cooldown
        ],
    },
    soak: {
        // Long duration at nominal load
        executor: 'constant-arrival-rate',
        rate: 4000,
        timeUnit: '1s',
        duration: '1h',
        preAllocatedVUs: 400,
        maxVUs: 1200,
    }
};

export const options = {
    scenarios: {
        [TEST_TYPE]: SCENARIOS[TEST_TYPE],
    },
    setupTimeout: '5m', // Valid for setup()
    thresholds: {
        dropped_iterations: ['count==0'],

        kafka_writer_error_count: ['count==0'],

        kafka_writer_write_seconds: ['p(95)<100'],

        kafka_writer_wait_seconds: ['p(95)<0.100', 'p(99)<0.200'],
    },
};

export function setup() {
    // 1. Topic Creation
    const connection = new Connection({
        address: brokers[0], // connect to the first broker
    });

    try {
        const topics = connection.listTopics();
        if (!topics.includes(topic)) {
            connection.createTopic({
                topic: topic,
                numPartitions: 4,
                replicationFactor: 4,
                config: {
                    "message.timestamp.type": "LogAppendTime",
                },
            });
        }
    } catch (e) {
        // If topic creation fails (e.g. exists), log but continue if possible or throw
        console.warn("Topic creation/check warning:", e);
    }

    connection.close();
    sleep(2); // Wait for metadata propagation

    // 2. Pre-serialization
    // Calculate max VUs needed across all scenarios to size the array
    // (Or just pick a safe upper bound like 2000 as per plan)
    const MAX_VUS = 2500;

    // Register schema ONCE here in setup
    const valueSchemaObject = schemaRegistry.createSchema({
        subject: "robot_data-avro-value",
        schema: schemaContent,
        schemaType: SCHEMA_TYPE_AVRO,
    });

    const messages = [];

    const now = Date.now(); // Fixed timestamp for all messages in this batch for pre-serialization trade-off

    for (let i = 0; i < MAX_VUS; i++) {
        const robot_id = `robot_${i + 1}`;
        // Deterministically pick a payload
        const rawPayloadIndex = i % rawData.length;

        // Clone object
        const payload = Object.assign({}, rawData[rawPayloadIndex]);

        // Set dynamic properties
        payload.robot_id = robot_id;
        payload.source_timestamp = now;

        const keyFn = schemaRegistry.serialize({
            data: robot_id,
            schemaType: SCHEMA_TYPE_STRING,
        });

        const valueFn = schemaRegistry.serialize({
            data: payload,
            schema: valueSchemaObject,
            schemaType: SCHEMA_TYPE_AVRO,
        });

        messages.push({
            key: keyFn,
            value: valueFn,
            robot_id: robot_id, // Store plain ID for metrics
        });
    }

    return messages;
}

export default function (data) {
    // data is the return value of setup()
    // __VU is 1-based, so use __VU - 1 as index
    // Use modular arithmetic just in case __VU > data.length (safety)
    const msg = data[(__VU - 1) % data.length];

    // Kafka Headers are strictly byte arrays ([]byte). They have no concept of "types" like Integer, Long, or Float.
    // If you send a raw Number from JavaScript (k6), you run into the Endianness Trap.
    // The Problem: Little Endian (JS) vs. Big Endian (Java/Network)
    // JavaScript (k6) runs on x86/ARM architectures, which are typically Little Endian.
    // Spark (Java/Scala) runs on the JVM, which is Big Endian by standard.
    // If you just throw a raw number into the header byte array, Spark might interpret the number 1 as 72,057,594,037,927,936 (byte reversal).
    const sentAt = Date.now().toString();
    try {
        writer.produce({
            messages: [{
                key: msg.key,
                value: msg.value,
                headers: {
                    "sent_at": sentAt,
                    "robot_id": msg.robot_id
                }
            }]
        });
    } catch (error) {
        // Errors will automatically increment kafka_writer_error_count
        console.error(`Produced failed: ${error}`);
    }
}

const ENV_TYPE = __ENV.ENV_TYPE || 'local';

export function handleSummary(data) {
    return {
        [`./results/summary-${ENV_TYPE}-${TEST_TYPE}.json`]: JSON.stringify(data, null, 2),
        stdout: textSummary(data, { indent: ' ', enableColors: true }),
    };
}

export function teardown(data) {
    writer.close();
}
