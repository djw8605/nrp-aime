# NRP AIME Backend

FastAPI backend for managing NRP allocations via the AIME/AMIE system.

## Requirements

- Python 3.11+
- PostgreSQL 14+

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run database migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload
```

## Running the AIME Worker

```bash
python -m workers.aime_worker
```

## API Documentation

Once running, visit http://localhost:8000/docs for interactive API docs.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://nrp:nrp@localhost:5432/nrp_aime` | PostgreSQL connection string |
| `PROMETHEUS_URL` | `https://prometheus.nrp-nautilus.io` | NRP Prometheus endpoint |
| `AMIE_SITE_NAME` | `NRP` | Site name for AMIE client |
| `AMIE_API_KEY` | `` | API key for AMIE client |
