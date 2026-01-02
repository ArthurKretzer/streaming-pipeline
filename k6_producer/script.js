import { Writer, SchemaRegistry, SCHEMA_TYPE_AVRO, SCHEMA_TYPE_STRING } from "k6/x/kafka";
import execution from 'k6/execution';
import { Trend } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';

// Load data and schema
const rawData = JSON.parse(open("./robot_data.json"));
let schemaContent = open("./schema.json");
// k6/JS uses float64 (double), so we need to adjust the schema
schemaContent = schemaContent.replace(/"type":\s*"float"/g, '"type": "double"');

const brokers = (__ENV.BROKERS || "172.16.208.242:31289").split(",");
const topic = "robot_data-avro";

const writer = new Writer({
    brokers: brokers,
    topic: topic,
    autoCreateTopic: true,
    batchSize: 1, // Must be 1 to measure per-message ack time accurately
    requiredAcks: 1, // Leader ack. Use -1 for all ISR if desired.
});

const schemaRegistry = new SchemaRegistry({
    url: __ENV.SCHEMA_REGISTRY_URL || "http://172.16.208.242:32081",
});

// Create the value schema once
const valueSchemaObject = schemaRegistry.createSchema({
    subject: "robot_data-avro-value",
    schema: schemaContent,
    schemaType: SCHEMA_TYPE_AVRO,
});

// Pre-serialize messages for 100 robots to avoid runtime overhead
const PRE_SERIALIZED_COUNT = 100;
const preSerializedMessages = [];

// Initialize pre-serialized messages
for (let i = 0; i < PRE_SERIALIZED_COUNT; i++) {
    // Deterministically pick a payload from the dataset
    // We use modulo to cycle through rawData if PRE_SERIALIZED_COUNT > rawData.length
    const rawPayloadIndex = i % rawData.length;
    // Clone the object to avoid mutating the original source
    const payload = Object.assign({}, rawData[rawPayloadIndex]);

    // Set timestamp to now (integer ms) - this will be static for the test duration
    payload.source_timestamp = Date.now();

    // The key should correspond to the robot ID.
    const robotId = `robot-${i}`;

    preSerializedMessages.push({
        key: schemaRegistry.serialize({
            data: robotId,
            schemaType: SCHEMA_TYPE_STRING,
        }),
        value: schemaRegistry.serialize({
            data: payload,
            schema: valueSchemaObject,
            schemaType: SCHEMA_TYPE_AVRO,
        }),
    });
}

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
    average: {
        // 100 robots at 10 Hz = 1000 msg/s
        executor: 'constant-arrival-rate',
        rate: 1000,
        timeUnit: '1s',
        duration: '10m', // Warmup included implicitly by running longer
        preAllocatedVUs: 50,
        maxVUs: 200,
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

export default function () {
    // Select a deterministic robot ID based on VU ID to distribute load
    const messageIndex = (__VU - 1) % PRE_SERIALIZED_COUNT;
    const message = preSerializedMessages[messageIndex];

    const start = Date.now();
    try {
        writer.produce({ messages: [message] });
        const latency = Date.now() - start;
        ackTrend.add(latency);
    } catch (error) {
        // Errors will automatically increment kafka_writer_error_count
        console.error(`Produced failed: ${error}`);
    }
}

const ENV_TYPE = __ENV.ENV_TYPE || 'local';

export function handleSummary(data) {
    return {
        [`summary-${ENV_TYPE}-${TEST_TYPE}.json`]: JSON.stringify(data, null, 2),
        stdout: textSummary(data, { indent: ' ', enableColors: true }),
    };
}

export function teardown(data) {
    writer.close();
}
