# NRP AIME Frontend

Vue 3 dashboard for managing NRP allocations.

## Requirements

- Node.js 18+

## Setup

```bash
npm install
npm run dev
```

## Build for production

```bash
npm run build
```

The backend API must be running at `http://localhost:8000` (or configure `VITE_API_BASE_URL`).

## Pages

- **/** — Projects list
- **/projects/:id** — Project detail with users and resource usage
