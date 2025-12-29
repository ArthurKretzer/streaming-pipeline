use clap::Parser;
use dotenvy::dotenv;
use log::info;
use tokio::signal;

mod config;
mod producer;

use config::Config;
use producer::Producer;

#[tokio::main]
async fn main() {
    dotenv().ok();
    env_logger::init();

    let config = Config::parse();
    info!("Starting Rust Producer with config: {:?}", config);

    let producer = Producer::new(config.clone());
    
    // Run producer in background
    let producer_clone = producer.clone();
    let _producer_handle = tokio::spawn(async move {
        producer_clone.run().await;
    });

    // Wait for Ctrl+C
    match signal::ctrl_c().await {
        Ok(()) => {
            info!("Shutting down...");
        }
        Err(err) => {
            eprintln!("Unable to listen for shutdown signal: {}", err);
        }
    }
    
    // Save stats
    producer.save_stats();
}
