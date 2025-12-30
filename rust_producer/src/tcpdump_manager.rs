use std::fs;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use chrono::Local;
use log::{error, info};
use crate::config::Config;

pub struct TcpDumpManager {
    enabled: bool,
    interface: String,
    output_path: String,
    target_host: String,
    process: Option<Child>,
    capture_file: Option<String>,
}

impl TcpDumpManager {
    pub fn new(config: &Config) -> Self {
        let target_host = config.target_host.clone().unwrap_or_else(|| {
            config.bootstrap_servers
                .split(':')
                .next()
                .unwrap_or("localhost")
                .to_string()
        });

        Self {
            enabled: config.tcpdump_enabled,
            interface: config.tcpdump_interface.clone(),
            output_path: config.tcpdump_output_path.clone(),
            target_host,
            process: None,
            capture_file: None,
        }
    }

    pub fn start(&mut self) {
        if !self.enabled {
            return;
        }

        if !Path::new(&self.output_path).exists() {
            match fs::create_dir_all(&self.output_path) {
                Ok(_) => {},
                Err(e) => {
                    error!("Failed to create output directory {}: {}", self.output_path, e);
                    return;
                }
            }
        }

        let timestamp = Local::now().format("%Y%m%d_%H%M%S");
        let capture_file = format!("{}/experiment_capture_{}.pcap", self.output_path, timestamp);
        self.capture_file = Some(capture_file.clone());

        info!("Starting tcpdump on interface {} filtering host {}", self.interface, self.target_host);

        match Command::new("tcpdump")
            .arg("-i")
            .arg(&self.interface)
            .arg("-w")
            .arg(&capture_file)
            .arg("host")
            .arg(&self.target_host)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(child) => {
                info!("Packet capture started. Saving to: {}", capture_file);
                self.process = Some(child);
            }
            Err(e) => {
                error!("Failed to start tcpdump: {}", e);
                self.process = None;
            }
        }
    }

    pub fn stop(&mut self) {
        if !self.enabled {
            return;
        }

        if let Some(mut child) = self.process.take() {
            info!("Stopping tcpdump...");
            match child.kill() {
                Ok(_) => {
                    match child.wait() {
                        Ok(_) => info!("tcpdump stopped successfully."),
                        Err(e) => error!("Failed to wait for tcpdump process: {}", e),
                    }
                }
                Err(e) => error!("Failed to kill tcpdump process: {}", e),
            }
        }
    }
}

impl Drop for TcpDumpManager {
    fn drop(&mut self) {
        self.stop();
    }
}
