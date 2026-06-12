# Frontend - React + Vite

```bash
cd frontend
npm install
npm run dev
```

The app defaults to backend `http://localhost:8000` during Vite development.
The container runtime writes `env-config.js` from `API_BASE` and renders the
Nginx `/api/` proxy from `NGINX_API_UPSTREAM`; Docker Compose points the proxy
to `http://backend:8000`, while Azure points it to the deployed backend HTTPS
URL.

Workflow Studio runtime info:

- Runtime badge reads backend `/health` metadata to display active environment/mode.
- In deployed frontend containers the badge uses proxied `/api/health` first so
  it does not read the frontend container's own `/health` endpoint.

UI highlights:

- Workflow history uses paginated API calls (`/api/workflows?page=<n>&page_size=<n>`).
- Event timeline uses rich SSE (`/api/chat/stream/{thread_id}/rich`) for live updates, while polling details remains as fallback.
- Right panel includes a RAG Evidence view that surfaces retrieved policy evidence and chunk IDs from workflow events/details when available.
