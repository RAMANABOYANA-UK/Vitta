# Vitta Frontend

Static HTML/CSS/JS that provides the user-facing interface for bill upload,
analysis result visualization, and appeal letter editing.

## Serving locally

Open `index.html` directly in a browser, **or** serve the directory with
any simple HTTP server (recommended so relative asset paths resolve cleanly):

```bash
# Python (simplest)
python -m http.server 8080

# Node / npx serve
npx serve -l 8080
```

Then visit: http://localhost:8080

## Structure

```
frontend/
├── index.html       # Landing page
├── app.html         # Main app (dashboard, bill detail, appeal editor)
├── login.html       # Sign-in / sign-up page
├── css/
│   ├── styles.css   # Global styles
│   └── app.css      # App-specific styles
└── js/
    ├── landing.js   # Landing page interactivity
    ├── api.js       # API contract + mock backend layer
    └── app.js       # Main app interactivity
```

## Backend API

The frontend expects the backend API to be running on `http://localhost:8000`
(configure via the `VITTA_API_URL` query parameter or the `VITTA_API_MODE`
global, see `js/api.js`).

Authentication uses a bearer token:
```
Authorization: Bearer dev-token-change-me
```
