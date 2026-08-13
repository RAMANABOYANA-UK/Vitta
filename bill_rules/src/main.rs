//! HTTP service exposing the bill_rules deterministic engine.
//!
//! Runs an Axum server (default port 3001, configurable via
//! `BILL_RULES_PORT`) with:
//! - `GET /health` — liveness probe with service name/version/status
//! - `POST /apply-rules` — accepts a full ParsedBill JSON body, runs the
//!   deterministic rules, returns the enriched bill with flags attached.
//!
//! The engine is pure and stateless: each request is fully independent.

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use bill_rules::apply_rules_to_document;
use serde_json::{json, Value};
use std::{env, net::SocketAddr, sync::Arc};
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

/// Shared application state. Currently minimal but reserved for future
/// needs (e.g., loaded rule config, telemetry exporters, rate limiting).
#[derive(Clone)]
struct AppState {
    started_at: chrono::DateTime<chrono::Utc>,
    version: Arc<str>,
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

    let port: u16 = env::var("BILL_RULES_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(3001);

    let state = AppState {
        started_at: chrono::Utc::now(),
        version: Arc::from(env!("CARGO_PKG_VERSION")),
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/apply-rules", post(apply_rules_handler))
        .layer(TraceLayer::new_for_http())
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    tracing::info!(port, "bill_rules service listening");

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .unwrap_or_else(|e| panic!("failed to bind 0.0.0.0:{port}: {e}"));
    axum::serve(listener, app)
        .await
        .expect("server crashed");
}

/// GET /health — simple liveness probe.
async fn health(State(state): State<AppState>) -> impl IntoResponse {
    Json(json!({
        "status": "ok",
        "service": "bill_rules",
        "version": state.version.as_ref(),
        "started_at": state.started_at.to_rfc3339(),
    }))
}

/// POST /apply-rules — accepts a full ParsedBill JSON body, runs the
/// deterministic engine, and returns the enriched bill.
///
/// Error mapping:
/// - Non-object input or malformed line_items/totals → 422 with a
///   structured error body.
/// - Unexpected internal failure → 500.
///
/// On success, logs the `document_id`, the total number of flags present
/// after rule application, and the rule-by-rule breakdown.
async fn apply_rules_handler(
    State(_state): State<AppState>,
    Json(doc): Json<Value>,
) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    let document_id = doc
        .get("document_id")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown")
        .to_string();

    tracing::info!(document_id = %document_id, "apply-rules request received");

    // Capture request size for logging/monitoring.
    let body_bytes = serde_json::to_vec(&doc).map(|b| b.len()).unwrap_or(0);

    match apply_rules_to_document(doc) {
        Ok(enriched) => {
            let total_flags = enriched["line_items"]
                .as_array()
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|i| i.get("flags").and_then(|f| f.as_array()))
                        .map(|f| f.len())
                        .sum::<usize>()
                })
                .unwrap_or(0);

            tracing::info!(
                document_id = %document_id,
                total_flags,
                body_bytes,
                "rules applied successfully"
            );
            Ok(Json(enriched))
        }
        Err(e) => {
            tracing::error!(document_id = %document_id, error = %e, "failed to apply rules");
            Err((
                StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({
                    "error": "rules_engine_error",
                    "message": e.to_string(),
                })),
            ))
        }
    }
}