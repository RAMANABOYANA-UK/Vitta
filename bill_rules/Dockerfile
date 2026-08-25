# Vitta — bill_rules (Rust deterministic rules engine)
# Multi-stage: build with the full Rust toolchain, run on a minimal image.
FROM rust:1.98-slim AS build
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
# Build with no default features to keep the artifact small; the service entry
# is the Axum binary (see Cargo.toml [[bin]] bill_rules_service).
RUN cargo build --release --bins

FROM debian:bookworm-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/target/release/bill_rules_service /usr/local/bin/bill_rules_service

EXPOSE 3001
CMD ["bill_rules_service"]