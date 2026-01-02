import { Writer, Connection, SchemaRegistry, SCHEMA_TYPE_AVRO, SCHEMA_TYPE_STRING } from "k6/x/kafka";
import execution from 'k6/execution';
import { Trend } from 'k6/metrics';
import { sleep } from 'k6';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';

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
    batchSize: 1, // Must be 1 to measure per-message ack time accurately
    requiredAcks: 1, // Leader ack. Use -1 for all ISR if desired.
});

const schemaRegistry = new SchemaRegistry({
    url: __ENV.SCHEMA_REGISTRY_URL || "http://172.16.208.242:32081",
});

// Custom trends
const ackTrend = new Trend('ack_latency');

const TEST_TYPE = __ENV.TEST_TYPE || 'smoke';

const SCENARIOS = {
    smoke: {
        executor: 'constant-arrival-rate',
        rate: 1,
        timeUnit: '1s',
        duration: '1m',
        preAllocatedVUs: 1,
        maxVUs: 5,
    },
    stress: {
        // Push beyond average in steps: 1k -> 2k -> 5k -> 10k
        executor: 'ramping-arrival-rate',
        startRate: 1000,
        timeUnit: '1s',
        preAllocatedVUs: 100,
        maxVUs: 1000,
        stages: [
            { target: 1000, duration: '5m' }, // Steady at average
            { target: 2000, duration: '5m' }, // 2x load
            { target: 5000, duration: '5m' }, // 5x load
            { target: 10000, duration: '5m' }, // 10x load
        ],
    },
    breakpoint: {
        // Ramp up to find max sustainable rate
        executor: 'ramping-arrival-rate',
        startRate: 1000,
        timeUnit: '1s',
        preAllocatedVUs: 200,
        maxVUs: 2000,
        stages: [
            { target: 20000, duration: '15m' }, // Linear ramp to 20k to find breakpoint
        ],
    },
    spike: {
        executor: 'ramping-arrival-rate',
        startRate: 1000,
        timeUnit: '1s',
        preAllocatedVUs: 100,
        maxVUs: 2000,
        stages: [
            { target: 1000, duration: '1m' }, // Warm up
            { target: 15000, duration: '30s' }, // Spike to 15x load
            { target: 15000, duration: '1m' }, // Sustain spike
            { target: 1000, duration: '30s' }, // Scale down / Recovery
            { target: 1000, duration: '1m' }, // Cooldown
        ],
    },
    soak: {
        // Long duration at nominal load
        executor: 'constant-arrival-rate',
        rate: 4000,
        timeUnit: '1s',
        duration: '1h',
        preAllocatedVUs: 50,
        maxVUs: 200,
    }
};

export const options = {
    scenarios: {
        [TEST_TYPE]: SCENARIOS[TEST_TYPE],
    },
    setupTimeout: '5m', // Valid for setup()
    thresholds: {
        // 1) Injection fidelity: if this fails, k6 did not achieve your configured rate.
        // dropped_iterations: ['count==0'],

        // 2) Kafka acceptance
        // kafka_writer_error_count: ['count==0'],

        // 3) Producer-side produce duration: set a conservative bound first, then tighten empirically.
        // This is where you will see the breakpoint emerge.
        // kafka_writer_write_seconds: ['p(95)<0.100'],

        // Monitor ack wait time specifically as requested
        // kafka_writer_wait_seconds: ['p(95)<0.050', 'p(99)<0.100'],

        // 3) Latency check (soft failure)
        ack_latency: ['p(95)<1000'], // 1s max ack time as sanity check
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

    const start = Date.now();

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
        const latency = Date.now() - start;
        ackTrend.add(latency, {
            robot_id: msg.robot_id,
            environment: ENV_TYPE,
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
