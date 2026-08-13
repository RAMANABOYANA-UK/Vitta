use axum::{extract::State, http::StatusCode, response::IntoResponse, routing::{get, post}, Json, Router};
use bill_rules::apply_rules_to_document;
use serde_json::{json, Value};
use std::{env, net::SocketAddr, sync::Arc};
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[derive(Clone)]
struct AppState { version: Arc<str> }

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "bill_rules=info,tower_http=info".into()))
        .with(tracing_subscriber::fmt::layer())
        .init();

    let port: u16 = env::var("BILL_RULES_PORT").ok().and_then(|p| p.parse().ok()).unwrap_or(3001);
    let state = AppState { version: Arc::from(env!("CARGO_PKG_VERSION")) };

    let app = Router::new()
        .route("/health", get(health))
        .route("/apply-rules", post(apply_rules_handler))
        .layer(TraceLayer::new_for_http())
        .layer(CorsLayer::new().allow_origin(Any).allow_methods(Any).allow_headers(Any))
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    tracing::info!("bill_rules service listening on {}", addr);
    let listener = tokio::net::TcpListener::bind(addr).await.expect("port already in use?");
    axum::serve(listener, app).await.unwrap();
}

async fn health(State(state): State<AppState>) -> impl IntoResponse {
    Json(json!({ "status": "ok", "service": "bill_rules", "version": state.version.as_ref() }))
}

async fn apply_rules_handler(Json(doc): Json<Value>) -> Result<impl IntoResponse, (StatusCode, Json<Value>)> {
    let document_id = doc.get("document_id").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
    tracing::info!(document_id = %document_id, "Applying rules");

    match apply_rules_to_document(doc) {
        Ok(enriched) => {
            let total_flags = enriched["line_items"].as_array()
                .map(|items| items.iter().filter_map(|i| i.get("flags").and_then(|f| f.as_array())).map(|f| f.len()).sum::<usize>())
                .unwrap_or(0);
            tracing::info!(document_id = %document_id, total_flags, "Rules applied successfully");
            Ok(Json(enriched))
        }
        Err(e) => {
            tracing::error!(document_id = %document_id, error = %e, "Failed to apply rules");
            Err((StatusCode::UNPROCESSABLE_ENTITY, Json(json!({"error": "rules_engine_error", "message": e.to_string()}))))
        }
    }
}