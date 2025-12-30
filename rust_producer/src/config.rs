use clap::Parser;

#[derive(Parser, Debug, Clone)]
#[command(author, version, about, long_about = None)]
pub struct Config {
    /// Kafka bootstrap servers
    #[arg(long, env = "KAFKA_BROKER", default_value = "localhost:9092")]
    pub bootstrap_servers: String,

    /// Schema Registry URL
    #[arg(long, env = "SCHEMA_REGISTRY_URI", default_value = "http://localhost:8081")]
    pub schema_registry_uri: String,

    /// Kafka topic name
    #[arg(long, env = "KAFKA_TOPIC", default_value = "robot_data")]
    pub topic_name: String,

    /// Number of robots to simulate
    #[arg(long, default_value_t = 1)]
    pub robots: usize,

    /// Frequency of messages per robot (Hz)
    #[arg(long, default_value_t = 10)]
    pub frequency: u64,

    /// Data type to produce
    #[arg(long, default_value = "robot_data")]
    pub data_type: String,

    /// Path to parquet dataset
    #[arg(long, default_value = "/app/dataset/robot_data.parquet")]
    pub dataset_path: String,

    /// Path to Avro schema
    #[arg(long, default_value = "/app/schemas/robot_data.json")]
    pub schema_path: String,

    /// Enable tcpdump packet capture
    #[arg(long, env = "ENABLE_TCPDUMP", default_value_t = false)]
    pub tcpdump_enabled: bool,

    /// Network interface for tcpdump
    #[arg(long, default_value = "eth0")]
    pub tcpdump_interface: String,

    /// Directory for tcpdump output
    #[arg(long, env = "TCPDUMP_OUTPUT_PATH", default_value = "tcpdump_output")]
    pub tcpdump_output_path: String,

    /// Target host to filter packets
    #[arg(long)]
    pub target_host: Option<String>,
}
