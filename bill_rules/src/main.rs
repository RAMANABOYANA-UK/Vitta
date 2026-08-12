//! HTTP service exposing the bill_rules deterministic engine.
//!
//! Runs an Axum server on port 3001 with:
//! - `GET /health` — liveness/readiness probe
//! - `POST /apply-rules` — accepts a `ParsedBill` JSON body, returns the
//!   enriched bill with deterministic flags attached.
//!
//! The engine is pure and stateless: each request is fully independent.

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use std::sync::Arc;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use bill_rules::{apply_rules, ParsedBill};

/// Shared application state. Currently minimal but reserved for future needs
/// (e.g., loaded rule config, telemetry exporters, rate limiting).
#[derive(Clone)]
struct AppState {
    started_at: chrono::DateTime<chrono::Utc>,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "bill_rules=info,tower_http=info".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let state = AppState {
        started_at: chrono::Utc::now(),
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/apply-rules", post(apply_rules_handler))
        .with_state(Arc::new(state))
        .layer(TraceLayer::new_for_http())
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        );

    let addr = std::net::SocketAddr::from(([0, 0, 0, 0], 3001));
    tracing::info!("bill_rules service listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind 0.0.0.0:3001");
    axum::serve(listener, app)
        .await
        .expect("server crashed");
}

/// GET /health — simple liveness probe.
async fn health(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    Json(serde_json::json!({
        "status": "ok",
        "service": "bill_rules",
        "version": env!("CARGO_PKG_VERSION"),
        "started_at": state.started_at.to_rfc3339(),
    }))
}

/// POST /apply-rules — accepts a ParsedBill, runs the deterministic engine,
/// returns the enriched bill.
///
/// Error mapping:
/// - Invalid JSON / schema mismatch → 400 with a human-readable message
/// - Internal engine failure → 500
async fn apply_rules_handler(
    State(_state): State<Arc<AppState>>,
    Json(bill): Json<ParsedBill>,
) -> Result<impl IntoResponse, (StatusCode, String)> {
    tracing::info!(
        document_id = %bill.document_id,
        line_items = bill.line_items.len(),
        "apply-rules request received"
    );

    let enriched = apply_rules(bill);

    let total_flags = enriched.total_flags();
    tracing::info!(
        document_id = %enriched.document_id,
        total_flags,
        "rules applied successfully"
    );

    Ok(Json(enriched))
}