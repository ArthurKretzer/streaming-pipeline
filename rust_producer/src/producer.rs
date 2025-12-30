use std::fs::File;
use std::sync::{Arc, Mutex};
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
use rdkafka::producer::{FutureProducer, FutureRecord};
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
    records: Arc<Vec<Value>>,
    encoder: Arc<AvroEncoder<'static>>,
    schema_content: String,
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
            .set("linger.ms", "10")
            .set("batch.num.messages", "10000")
            .set("queue.buffering.max.messages", "500000")
            .set("compression.type", "none")
            .set("max.in.flight.requests.per.connection", "5")
            .set("message.timeout.ms", "5000")
            .create()
            .expect("Producer creation error");

        let records = Self::load_dataset(&config.dataset_path);

        // Initialize Schema Registry Encoder
        let sr_settings = SrSettings::new(config.schema_registry_uri.clone());
        let encoder = Arc::new(AvroEncoder::new(sr_settings));
        
        // Read Schema file
        let mut schema_content = String::new();
        let mut file = File::open(&config.schema_path).expect("Failed to open schema file");
        file.read_to_string(&mut schema_content).expect("Failed to read schema file");

        Self {
            config,
            topic_name,
            producer,
            records: Arc::new(records),
            encoder,
            schema_content,
            stats: Stats {
                ack_records: Arc::new(Mutex::new(Vec::new())),
            },
        }
    }

    fn load_dataset(path: &str) -> Vec<Value> {
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
            records.push(Value::Object(map));
        }

        info!("Loaded {} records", records.len());
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
            let raw_schema = self.schema_content.clone();

            let handle = tokio::spawn(async move {
                let mut interval = time::interval(Duration::from_secs_f64(1.0 / frequency as f64));
                // Random start delay to avoid thundering herd
                time::sleep(Duration::from_millis(rand::random::<u64>() % 1000)).await;
                
                // Parse schema once per thread
                let schema = apache_avro::Schema::parse_str(&raw_schema).expect("Failed to parse schema");

                // Cycle through records indefinitely
                for record in records.iter().cycle() {
                    interval.tick().await;

                    let mut msg = record.clone();
                    let now = SystemTime::now();
                    let timestamp_ms = now.duration_since(UNIX_EPOCH).unwrap().as_millis() as i64;
                    // Format as ISO string for source_timestamp
                    let now_dt: DateTime<Utc> = now.into();
                    
                    if let Some(obj) = msg.as_object_mut() {
                        obj.insert("source_timestamp".to_string(), json!(now_dt.to_rfc3339()));
                        obj.insert("robot_id".to_string(), json!(robot_id));
                    }

                    let avro_val = to_value(&msg).expect("Failed to convert to avro value");
                    let avro_val = avro_val.resolve(&schema).expect("Failed to resolve schema");

                    let fields = match avro_val {
                        apache_avro::types::Value::Record(fields) => fields,
                        _ => panic!("Schema must be a record"),
                    };
                    
                    // Convert Vec<(String, Value)> to Vec<(&str, Value)>
                    let fields_ref: Vec<(&str, apache_avro::types::Value)> = fields.iter()
                        .map(|(k, v)| (k.as_str(), v.clone()))
                        .collect();

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
                        // Success
                        info!("Message sent successfully for robot {}", robot_id);
                        let latency = t_send.elapsed().as_secs_f64();
                        let mut ack_records = stats.ack_records.lock().unwrap();
                        ack_records.push(AckRecord {
                            source_timestamp: timestamp_ms,
                            robot_id,
                            ack_latency: latency,
                        });
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
}
