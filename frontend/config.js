// Default runtime config — points to same-origin /api (works behind the local
// nginx/Docker proxy). The Render build (build.sh) overwrites this file with the
// actual deployed backend URL (window.AVIRA_CONFIG.backendUrl).
window.AVIRA_CONFIG = { backendUrl: "/api" };
