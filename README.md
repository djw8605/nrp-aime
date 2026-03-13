# nrp-aime

NRP AIME Allocation Manager — a full-stack web application for managing allocations in the National Research Platform (NRP).

## Overview

This system interfaces with the AIME allocation and accounting system. It receives allocation packets, creates projects, assigns users, and displays usage information from the NRP accounting system.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python) |
| Database | PostgreSQL + SQLAlchemy (ORM) + Alembic (migrations) |
| Allocation ingestion | AMIE client (`amieclient`) |
| Usage metrics | Prometheus (NRP endpoint) |
| Frontend | Vue 3 + TailwindCSS + Axios |
| Container orchestration | Docker Compose |

## Project Structure

```
nrp-aime/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── main.py           # Application entry point
│   │   ├── config.py         # Settings (env vars)
│   │   ├── database.py       # DB engine & session
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── api/              # FastAPI route handlers
│   │   └── services/
│   │       ├── aime/         # AMIE packet ingestion
│   │       ├── prometheus/   # NRP metrics queries
│   │       └── authentik/    # Account email stub
│   ├── migrations/           # Alembic migrations
│   ├── workers/              # Background task workers
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/                 # Vue 3 dashboard
│   ├── src/
│   │   ├── api/              # Axios API client modules
│   │   ├── components/       # Reusable Vue components
│   │   ├── views/            # Page-level Vue views
│   │   └── router/           # Vue Router configuration
│   ├── package.json
│   └── vite.config.js
└── docker-compose.yml        # Local development stack
```

## Quick Start (Docker Compose)

```bash
# Start all services (PostgreSQL, FastAPI backend, Vue frontend)
docker-compose up

# In a separate terminal, run database migrations
docker-compose exec backend alembic upgrade head
```

Then visit:
- **Frontend**: http://localhost:5173
- **API docs**: http://localhost:8000/docs

## Manual Setup

### Backend

```bash
cd backend
pip install -r requirements.txt

# Set environment variables (or create a .env file)
export DATABASE_URL=postgresql://nrp:nrp@localhost:5432/nrp_aime
export PROMETHEUS_URL=https://prometheus.nrp-nautilus.io

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/projects/` | List all projects |
| GET | `/api/v1/projects/{id}` | Get project details |
| GET | `/api/v1/projects/{id}/users` | List users for a project |
| GET | `/api/v1/projects/{id}/usage` | Get CPU/GPU usage from Prometheus |
| POST | `/api/v1/projects/{id}/send-account-email` | Queue account creation emails |
| POST | `/api/v1/users/` | Create a user |
| GET | `/api/v1/users/{id}` | Get user details |
| GET | `/healthz` | Health check |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://nrp:nrp@localhost:5432/nrp_aime` | PostgreSQL connection string |
| `PROMETHEUS_URL` | `https://prometheus.nrp-nautilus.io` | NRP Prometheus endpoint |
| `AMIE_SITE_NAME` | `NRP` | Site name for AMIE client |
| `AMIE_API_KEY` | `` | API key for AMIE client |
| `DEBUG` | `false` | Enable debug mode |

## Architecture Notes

- The **PostgreSQL database** acts as the central interface between the frontend dashboard and the backend services.
- The **AIME worker** (`workers/aime_worker.py`) polls AMIE for new allocation packets and persists them as Project + User records.
- The **Prometheus service** queries namespace-scoped pod metrics to report CPU/GPU usage.
- The **Authentik service** (`services/authentik/service.py`) is currently a stub that logs email requests; it will be wired to Authentik flows in a future iteration.
