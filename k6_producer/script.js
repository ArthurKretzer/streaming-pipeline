import { Writer, SchemaRegistry, SCHEMA_TYPE_AVRO, SCHEMA_TYPE_STRING } from "k6/x/kafka";
import execution from 'k6/execution';
import { Trend } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';

// Load data and schema
const rawData = JSON.parse(open("./dataset/robot_data.json"));
let schemaContent = open("./schemas/schema.json");
// k6/JS uses float64 (double), so we need to adjust the schema
schemaContent = schemaContent.replace(/"type":\s*"float"/g, '"type": "double"');

const brokers = (__ENV.BROKERS || "172.16.208.242:31289").split(",");
console.info(`Broker: ${brokers}`);
console.info(`Schema registry: ${__ENV.SCHEMA_REGISTRY_URL}`);
console.info(`Test type: ${__ENV.TEST_TYPE}`);
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
console.info(`Creating schema...`);
const valueSchemaObject = schemaRegistry.createSchema({
    subject: "robot_data-avro-value",
    schema: schemaContent,
    schemaType: SCHEMA_TYPE_AVRO,
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

console.info(`Starting test ${TEST_TYPE}...`);
export default function () {
    const robot_id = `robot_${__VU}`;
    // Deterministically pick a payload from the dataset
    const rawPayloadIndex = (__VU - 1) % rawData.length;

    // Clone the object to avoid mutating the original source
    const payload = Object.assign({}, rawData[rawPayloadIndex]);

    // Set dynamic properties
    payload.robot_id = robot_id;
    payload.source_timestamp = Date.now();

    const key = schemaRegistry.serialize({
        data: robot_id,
        schemaType: SCHEMA_TYPE_STRING,
    });

    const value = schemaRegistry.serialize({
        data: payload,
        schema: valueSchemaObject,
        schemaType: SCHEMA_TYPE_AVRO,
    });

    const start = Date.now();
    try {
        writer.produce({
            messages: [{
                key: key,
                value: value,
            }]
        });
        const latency = Date.now() - start;
        ackTrend.add(latency, {
            robot_id: robot_id,
            source_timestamp: String(payload.source_timestamp),
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
