FROM rust:1.92-slim-bookworm AS builder
WORKDIR /app
# Install build dependencies
RUN apt-get update && apt-get install -y pkg-config libssl-dev cmake g++

# Copy source code
COPY rust_producer/ .

# Build release
RUN cargo build --release

# Runtime image
FROM debian:bookworm-slim
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y libssl3 ca-certificates tcpdump && rm -rf /var/lib/apt/lists/*

# Copy binary
COPY --from=builder /app/target/release/rust_producer .
COPY --from=builder /app/dataset /app/dataset
COPY --from=builder /app/schemas /app/schemas

# Default command
CMD ["/app/rust_producer"]
