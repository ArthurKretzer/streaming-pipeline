import { Writer, SchemaRegistry, SCHEMA_TYPE_AVRO, SCHEMA_TYPE_STRING } from "k6/x/kafka";

// Load data and schema
const rawData = JSON.parse(open("./robot_data.json"));
let schemaContent = open("./schema.json");
// k6/JS uses float64 (double), so we need to adjust the schema
schemaContent = schemaContent.replace(/"type":\s*"float"/g, '"type": "double"');

const brokers = ["172.16.208.242:31289"];
const topic = "robot_data-avro";

const writer = new Writer({
    brokers: brokers,
    topic: topic,
    autoCreateTopic: true,
});

const schemaRegistry = new SchemaRegistry({
    url: "http://172.16.208.242:32081",
});

// Create the value schema once
const valueSchemaObject = schemaRegistry.createSchema({
    subject: "robot_data-avro-value-optimized",
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
    // Clone the object to avoid mutating the original source (though distinct load is already immutable-ish)
    // Actually, JSON.parse creates new objects, so accessing rawData[index] gets the same ref.
    // We create a new object.
    const payload = Object.assign({}, rawData[rawPayloadIndex]);

    // Set timestamp to now (integer ms) - this will be static for the test duration
    payload.source_timestamp = Date.now();
    // Set robot_action_id based on index (or keep from data, but user asked for deterministic robot id)
    // We'll trust the payload has reasonable data, but we use 'i' to map to a robot ID for the key.
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

export const options = {
    scenarios: {
        rate_10_vus_1: {
            executor: 'constant-arrival-rate',
            rate: 10,
            timeUnit: '1s',
            duration: '10m',
            preAllocatedVUs: 1,
            maxVUs: 1,
            startTime: '0s',
            gracefulStop: '10s',
        },
        rate_10_vus_10: {
            executor: 'constant-arrival-rate',
            rate: 100,
            timeUnit: '1s',
            duration: '10m',
            preAllocatedVUs: 10,
            maxVUs: 10,
            startTime: '2m',
            gracefulStop: '10s',
        },
        rate_10_vus_50: {
            executor: 'constant-arrival-rate',
            rate: 500,
            timeUnit: '1s',
            duration: '10m',
            preAllocatedVUs: 50,
            maxVUs: 50,
            startTime: '4m',
            gracefulStop: '10s',
        },
        rate_10_vus_100: {
            executor: 'constant-arrival-rate',
            rate: 1000,
            timeUnit: '1s',
            duration: '10m',
            preAllocatedVUs: 100,
            maxVUs: 100,
            startTime: '6m',
            gracefulStop: '10s',
        },
        rate_20_vus_100: {
            executor: 'constant-arrival-rate',
            rate: 2000,
            timeUnit: '1s',
            duration: '10m',
            preAllocatedVUs: 100,
            maxVUs: 100,
            startTime: '8m',
            gracefulStop: '10s',
        },
        rate_50_vus_100: {
            executor: 'constant-arrival-rate',
            rate: 5000,
            timeUnit: '1s',
            duration: '10m',
            preAllocatedVUs: 100,
            maxVUs: 100,
            startTime: '10m',
            gracefulStop: '10s',
        },
        rate_100_vus_100: {
            executor: 'constant-arrival-rate',
            rate: 10000,
            timeUnit: '1s',
            duration: '10m',
            preAllocatedVUs: 100,
            maxVUs: 100,
            startTime: '12m',
            gracefulStop: '10s',
        },
    },
    thresholds: {
        // 1) Injection fidelity: if this fails, k6 did not achieve your configured rate.
        dropped_iterations: ['rate>0.99'],

        // 2) Kafka acceptance: extension metrics (names can vary by version, verify in your output).
        // If your run produces any writer errors, the breakpoint is already exceeded.
        kafka_writer_error_count: ['rate>0.99'],

        // 2) Correctness via checks: you can check that writer.produce() returned without throwing.
        checks: ['rate>0.99'],

        // 3) Producer-side produce duration: set a conservative bound first, then tighten empirically.
        // This is where you will see the breakpoint emerge.
        kafka_writer_write_seconds: ['p(95)<0.050', 'p(99)<0.100'],
    },
};

export default function () {
    // Select a deterministic robot ID based on VU ID
    // __VU is 1-based, so subtract 1
    // We heavily reused messages if VUs > PRE_SERIALIZED_COUNT, but here we expect 100 VUs max matching 100 robots.
    // If we have more VUs, they will cycle through the robots.
    const messageIndex = (__VU - 1) % PRE_SERIALIZED_COUNT;
    const message = preSerializedMessages[messageIndex];

    writer.produce({ messages: [message] });
}

export function teardown(data) {
    writer.close();
}
