use clap::Parser;
use dotenvy::dotenv;
use tracing::info;
use tokio::signal;
use tokio::signal::unix::{signal, SignalKind};

mod config;
mod producer;
mod tcpdump_manager;

use config::Config;
use producer::Producer;
use tcpdump_manager::TcpDumpManager;

#[tokio::main]
async fn main() {
    dotenv().ok();

    // Initialize non-blocking logging
    let (non_blocking, _guard) = tracing_appender::non_blocking(std::io::stdout());
    tracing_subscriber::fmt()
        .with_writer(non_blocking)
        .init();

    let config = Config::parse();
    info!("Starting Rust Producer with config: {:?}", config);

    let mut tcpdump_manager = TcpDumpManager::new(&config);
    tcpdump_manager.start();

    let producer = Producer::new(config.clone());
    
    // Run producer in background
    let producer_clone = producer.clone();
    let _producer_handle = tokio::spawn(async move {
        producer_clone.run().await;
    });

    // Wait for Ctrl+C or SIGTERM
    let mut sigterm = signal(SignalKind::terminate()).expect("Failed to register SIGTERM handler");

    tokio::select! {
        _ = signal::ctrl_c() => {
            info!("Received Ctrl+C, shutting down...");
        }
        _ = sigterm.recv() => {
            info!("Received SIGTERM, shutting down...");
        }
    }
    
    // Flush producer
    producer.flush(std::time::Duration::from_secs(10));

    // Save stats
    producer.save_stats();
    
    // Stop tcpdump
    tcpdump_manager.stop();
}
