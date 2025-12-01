import os
import subprocess
from datetime import datetime

from common.logger import log

logger = log("TcpDumpManager")


class TcpDumpManager:
    """
    Manages the execution of tcpdump for packet capture.
    """

    def __init__(
        self,
        interface: str,
        output_path: str,
        target_host: str,
        enabled: bool = False,
    ):
        """
        Initializes the TcpDumpManager.

        Args:
            interface (str): Network interface to capture on.
            output_path (str): Directory to save pcap files.
            target_host (str): IP or hostname to filter by.
            enabled (bool): Whether packet capture is enabled.
        """
        self.interface = interface
        self.output_path = output_path
        self.target_host = target_host
        self.enabled = enabled
        self.process = None
        self.capture_file = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        """
        Starts the tcpdump process in the background.
        """
        if not self.enabled:
            return

        if not os.path.exists(self.output_path):
            try:
                os.makedirs(self.output_path)
            except OSError as e:
                logger.error(
                    f"Failed to create output directory {self.output_path}: "
                    f"{e}"
                )
                return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.capture_file = os.path.join(
            self.output_path, f"experiment_capture_{timestamp}.pcap"
        )

        # Construct the command
        # -i: Interface
        # -w: Write to file
        # host: Filter by host
        command = [
            "tcpdump",
            "-i",
            self.interface,
            "-w",
            self.capture_file,
            "host",
            self.target_host,
        ]

        try:
            logger.info(f"Starting tcpdump with command: {' '.join(command)}")
            self.process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            logger.info(
                f"Packet capture started. Saving to: {self.capture_file}"
            )
        except Exception as e:
            logger.error(f"Failed to start tcpdump: {e}")
            self.process = None

    def stop(self):
        """
        Stops the tcpdump process.
        """
        if not self.enabled or self.process is None:
            return

        logger.info("Stopping tcpdump...")
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "tcpdump did not terminate gracefully, killing..."
                )
                self.process.kill()
                self.process.wait()

            logger.info("tcpdump stopped successfully.")

            if os.path.exists(self.capture_file):
                size = os.path.getsize(self.capture_file)
                logger.info(
                    f"Capture file created: {self.capture_file} ({size} bytes)"
                )
            else:
                logger.warning(f"Capture file not found: {self.capture_file}")

        except Exception as e:
            logger.error(f"Error stopping tcpdump: {e}")
        finally:
            self.process = None
