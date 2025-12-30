use std::fs::File;
use std::sync::{Arc, Mutex};
use std::collections::HashMap;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use chrono::{DateTime, Utc};
use tracing::{info, warn};
use parquet::file::reader::{FileReader, SerializedFileReader};
use parquet::arrow::ArrowWriter;
use parquet::record::Row;
use arrow::array::{Int64Array, Int32Array, Float64Array};
use arrow::record_batch::RecordBatch;
use arrow::datatypes::{DataType, Field, Schema as ArrowSchema};
use rdkafka::config::ClientConfig;
use rdkafka::producer::{FutureProducer, FutureRecord, Producer as KafkaProducer};
use rdkafka::util::Timeout;
use serde_json::{json, Value};
use tokio::time;
use schema_registry_converter::async_impl::schema_registry::SrSettings;
use schema_registry_converter::async_impl::avro::AvroEncoder;
use schema_registry_converter::schema_registry_common::SubjectNameStrategy;
use apache_avro::to_value;
use std::io::Read;

use crate::config::Config;

#[derive(Clone)]
pub struct Stats {
    pub ack_records: Arc<Mutex<Vec<AckRecord>>>,
    pub robot_deltas: Arc<Mutex<HashMap<i32, Vec<f64>>>>,
}

#[derive(Clone, Debug)]
pub struct AckRecord {
    pub source_timestamp: i64,
    pub robot_id: i32,
    pub ack_latency: f64,
}

#[derive(Clone)]
pub struct Producer {
    config: Config,
    topic_name: String,
    producer: FutureProducer,
    records: Arc<Vec<apache_avro::types::Value>>,
    encoder: Arc<AvroEncoder<'static>>,
    stats: Stats,
}

impl Producer {
    pub fn new(config: Config) -> Self {
        let topic_name = format!("{}-avro", config.topic_name);

        let producer: FutureProducer = ClientConfig::new()
            .set("bootstrap.servers", &config.bootstrap_servers)
            .set("client.id", format!("{}-producer", config.topic_name))
            .set("acks", "1")
            .set("enable.idempotence", "false")
            .set("linger.ms", "0")
            .set("batch.num.messages", "10000")
            .set("queue.buffering.max.messages", "500000")
            .set("compression.type", "none")
            .set("max.in.flight.requests.per.connection", "5")
            .set("message.timeout.ms", "5000")
            .create()
            .expect("Producer creation error");

        // Read Schema file
        let mut schema_content = String::new();
        let mut file = File::open(&config.schema_path).expect("Failed to open schema file");
        file.read_to_string(&mut schema_content).expect("Failed to read schema file");
        
        let schema = apache_avro::Schema::parse_str(&schema_content).expect("Failed to parse schema");

        let records = Self::load_and_convert_dataset(&config.dataset_path, &schema);

        // Initialize Schema Registry Encoder
        let sr_settings = SrSettings::new(config.schema_registry_uri.clone());
        let encoder = Arc::new(AvroEncoder::new(sr_settings));

        Self {
            config,
            topic_name,
            producer,
            records: Arc::new(records),
            encoder,
            stats: Stats {
                ack_records: Arc::new(Mutex::new(Vec::new())),
                robot_deltas: Arc::new(Mutex::new(HashMap::new())),
            },
        }
    }

    fn load_and_convert_dataset(path: &str, schema: &apache_avro::Schema) -> Vec<apache_avro::types::Value> {
        info!("Loading dataset from {}", path);
        let file = File::open(path).expect("Failed to open parquet file");
        let reader = SerializedFileReader::new(file).expect("Failed to create parquet reader");
        let mut records = Vec::new();

        for row in reader.get_row_iter(None).expect("Failed to get row iter") {
            let row: Row = row.expect("Failed to read row");
            let mut map: serde_json::Map<String, Value> = serde_json::Map::new();
            
            for (name, field) in row.get_column_iter() {
                 let val = match field {
                    parquet::record::Field::Null => Value::Null,
                    parquet::record::Field::Bool(v) => json!(v),
                    parquet::record::Field::Byte(v) => json!(v),
                    parquet::record::Field::Short(v) => json!(v),
                    parquet::record::Field::Int(v) => json!(v),
                    parquet::record::Field::Long(v) => json!(v),
                    parquet::record::Field::Float(v) => json!(v),
                    parquet::record::Field::Double(v) => json!(v),
                    parquet::record::Field::Str(v) => json!(v),
                    parquet::record::Field::Bytes(v) => json!(v.data()),
                    _ => json!(format!("{:?}", field)), // Fallback
                };
                map.insert(name.to_string(), val);
            }
            
            // Insert dummy values for fields we will update later, to ensure schema resolution works
            map.insert("source_timestamp".to_string(), json!(""));
            map.insert("robot_id".to_string(), json!(0));

            let json_val = Value::Object(map);
            let avro_val = to_value(&json_val).expect("Failed to convert to avro value");
            let resolved_val = avro_val.resolve(schema).expect("Failed to resolve schema");
            
            records.push(resolved_val);
        }

        info!("Loaded and converted {} records", records.len());
        records
    }

    pub async fn run(&self) {
        let mut handles = vec![];
        let num_robots = self.config.robots;
        let records = self.records.clone(); // Cheap clone of Arc
        
        info!("Starting {} robot simulations...", num_robots);

        for i in 0..num_robots {
            let robot_id = i as i32;
            let producer = self.producer.clone();
            let topic = self.topic_name.clone();
            let frequency = self.config.frequency;
            let records = records.clone();
            let stats = self.stats.clone();

            let encoder = self.encoder.clone();

            let handle = tokio::spawn(async move {
                let mut interval = time::interval(Duration::from_secs_f64(1.0 / frequency as f64));
                // Random start delay to avoid thundering herd
                time::sleep(Duration::from_millis(rand::random::<u64>() % 1000)).await;

                let mut last_send_time: Option<Instant> = None;
                let mut local_deltas: Vec<f64> = Vec::with_capacity(1000);
                let mut local_acks: Vec<AckRecord> = Vec::with_capacity(100);
                
                // Cycle through records indefinitely
                for record in records.iter().cycle() {
                    interval.tick().await;

                    let mut msg = record.clone();
                    let now = SystemTime::now();
                    let timestamp_ms = now.duration_since(UNIX_EPOCH).unwrap().as_millis() as i64;
                    let now_dt: DateTime<Utc> = now.into();
                    let now_str = now_dt.to_rfc3339();

                    // Update fields directly in the Avro Value
                    match &mut msg {
                        apache_avro::types::Value::Record(fields) => {
                            for (name, value) in fields {
                                if name == "source_timestamp" {
                                    *value = apache_avro::types::Value::String(now_str.clone());
                                } else if name == "robot_id" {
                                    *value = apache_avro::types::Value::Int(robot_id);
                                }
                            }
                        },
                        _ => panic!("Unexpected Avro value type"),
                    }

                    // Extract payload for encoding
                    let fields_ref: Vec<(&str, apache_avro::types::Value)> = match &msg {
                        apache_avro::types::Value::Record(fields) => fields.iter()
                            .map(|(k, v)| (k.as_str(), v.clone()))
                            .collect(),
                        _ => unreachable!(),
                    };

                    let payload = encoder
                        .encode(
                            fields_ref,
                            SubjectNameStrategy::TopicNameStrategy(topic.clone(), false)
                        )
                        .await
                        .expect("Avro encoding failed");

                    let t_send = Instant::now();
                    
                    let delivery_status = producer.send(
                        FutureRecord::to(&topic)
                            .payload(&payload)
                            .key(&timestamp_ms.to_string()),
                        Timeout::After(Duration::from_secs(0)),
                    ).await;

                    if let Ok((_partition, _offset)) = delivery_status {
                        // Success - logic removed to improve performance
                        // info!("Message sent successfully for robot {}", robot_id); 
                        let latency = t_send.elapsed().as_secs_f64();

                        // Track inter-message delta
                        if let Some(last) = last_send_time {
                            let delta = t_send.duration_since(last).as_secs_f64();
                            local_deltas.push(delta);
                        }
                        last_send_time = Some(t_send);

                        // Buffer acknowledgment
                        local_acks.push(AckRecord {
                            source_timestamp: timestamp_ms,
                            robot_id,
                            ack_latency: latency,
                        });

                        // Periodically flush stats
                        if local_deltas.len() >= 1000 {
                            let mut all_deltas = stats.robot_deltas.lock().unwrap();
                            let robot_vec = all_deltas.entry(robot_id).or_insert_with(Vec::new);
                            robot_vec.append(&mut local_deltas);
                        }

                        if local_acks.len() >= 100 {
                           let mut ack_records = stats.ack_records.lock().unwrap();
                           ack_records.append(&mut local_acks);
                        }

                    } else {
                        warn!("Delivery failed for robot {}", robot_id);
                    }
                }
            });
            handles.push(handle);
        }

        // Wait for all tasks (they run indefinitely)
        for handle in handles {
            let _ = handle.await;
        }
    }

    pub fn flush(&self, timeout: Duration) {
        info!("Flushing producer messages...");
        let _ = self.producer.flush(timeout);
        info!("Producer flush completed");
    }

    pub fn save_stats(&self) {
        let stats = self.stats.ack_records.lock().unwrap();
        if stats.is_empty() {
             return;
        }
        
        info!("Collected {} ack latency records", stats.len());
        
        let timestamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        let filename = format!("/app/data/rust_ack_latency_{}.parquet", timestamp);
        let path = std::path::Path::new(&filename);
        let file = File::create(path).expect("Failed to create parquet file");

        // Convert stats to Arrow arrays
        let source_timestamps: Vec<i64> = stats.iter().map(|s| s.source_timestamp).collect();
        let robot_ids: Vec<i32> = stats.iter().map(|s| s.robot_id).collect();
        let ack_latencies: Vec<f64> = stats.iter().map(|s| s.ack_latency).collect();

        let source_timestamp_array = Arc::new(Int64Array::from(source_timestamps));
        let robot_id_array = Arc::new(Int32Array::from(robot_ids));
        let ack_latency_array = Arc::new(Float64Array::from(ack_latencies));

        let schema = Arc::new(ArrowSchema::new(vec![
            Field::new("source_timestamp", DataType::Int64, false),
            Field::new("robot_id", DataType::Int32, false),
            Field::new("ack_latency", DataType::Float64, false),
        ]));

        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![source_timestamp_array, robot_id_array, ack_latency_array],
        ).expect("Failed to create record batch");

        let mut writer = ArrowWriter::try_new(file, schema.clone(), None).expect("Failed to create arrow writer");
        writer.write(&batch).expect("Failed to write batch");
        writer.close().expect("Failed to close writer");
        
        info!("Saved stats to {}", filename);
    }

    pub fn print_report(&self) {
        let stats = self.stats.robot_deltas.lock().unwrap();
        if stats.is_empty() {
            info!("No robot stats collected.");
            return;
        }

        info!("--- Robot Inter-Message Interval Report ---");
        // Collect and sort robot IDs for consistent output
        let mut robot_ids: Vec<&i32> = stats.keys().collect();
        robot_ids.sort();

        for robot_id in robot_ids {
            let deltas = &stats[robot_id];
            if deltas.is_empty() {
                continue;
            }

            let min = deltas.iter().fold(f64::INFINITY, |a, &b| a.min(b));
            let max = deltas.iter().fold(f64::NEG_INFINITY, |a, &b| a.max(b));
            let sum: f64 = deltas.iter().sum();
            let avg = sum / deltas.len() as f64;
            
            let variance = deltas.iter().map(|value| {
                let diff = avg - (*value as f64);
                diff * diff
            }).sum::<f64>() / deltas.len() as f64;
            let std_dev = variance.sqrt();

            // Calculate median
            let mut sorted_deltas = deltas.clone();
            sorted_deltas.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let mid = sorted_deltas.len() / 2;
            let median = if sorted_deltas.len() % 2 == 0 {
                (sorted_deltas[mid - 1] + sorted_deltas[mid]) / 2.0
            } else {
                sorted_deltas[mid]
            };

            info!(
                "Robot {}: Count={}, Min={:.6}, Max={:.6}, Avg={:.6}, Median={:.6}, StdDev={:.6}",
                robot_id, deltas.len(), min, max, avg, median, std_dev
            );
        }
        info!("-------------------------------------------");
    }
}
