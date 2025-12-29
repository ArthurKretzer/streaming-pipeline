FROM rust:1.83-slim-bookworm as builder
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
RUN apt-get update && apt-get install -y libssl3 ca-certificates && rm -rf /var/lib/apt/lists/*

# Copy binary
COPY --from=builder /app/target/release/rust_producer .

# Default command
CMD ["./rust_producer"]
