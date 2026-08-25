# Vitta — frontend
# Static SPA served by nginx, which also reverse-proxies /api/v1 and /health to
# the backend so the browser talks to a single origin (no CORS surprises).
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html app.html login.html /usr/share/nginx/html/
COPY css /usr/share/nginx/html/css
COPY js /usr/share/nginx/html/js

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]