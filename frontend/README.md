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

- **/** — Projects list and top KPIs
- **/projects/:id** — Project detail with users and resource usage
- **/people** — People directory (searchable)
- **/people/:id** — Person detail and person-scoped invite action
- **/invite/accept** — Magic-link landing page with account summary
- **/invite/success** — Account-created success page with getting-started cards
- **/invite/error** — Invite flow error page
- **/admin** — Operational/admin dashboards
- **/packets/logs** — Packet log table (search/sort/paginated)
- **/packets/manual** — Manual packet input form
