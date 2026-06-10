# Frontend - React + Vite

```bash
cd frontend
npm install
npm run dev
```

The app expects backend at `http://localhost:8000`.

UI highlights:

- Workflow history uses paginated API calls (`/api/workflows?page=<n>&page_size=<n>`).
- Timeline and HITL behavior remain unchanged.
- Right panel includes a RAG Evidence view that surfaces retrieved policy evidence and chunk IDs from workflow events/details when available.
