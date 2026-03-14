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

## Running the Usage Export Worker

```bash
python -m workers.usage_worker
```

## Worker Status in Database

Worker heartbeat and runtime state are stored in the `worker_statuses` table.

Example query:

```sql
SELECT worker_name, is_active, current_state, status_message, last_heartbeat
FROM worker_statuses
ORDER BY worker_name;
```

## Project Usage Snapshots in Database

The usage worker continuously refreshes per-project usage in
`project_usage_snapshots`. These values are then used by API endpoints for
project usage and top-level KPI summaries.

Example query:

```sql
SELECT project_id, cpu_used_current, gpu_used_current, charge_interval, last_collected_at
FROM project_usage_snapshots
ORDER BY last_collected_at DESC;
```

Usage exports to AMIE are sent as interval deltas (`AdjustmentUsageRecord`
with `adjustment_type=debit`) for each collection interval, not as repeatedly
sent cumulative totals.

## API Documentation

Once running, visit http://localhost:8000/docs for interactive API docs.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://nrp:nrp@localhost:5432/nrp_aime` | PostgreSQL connection string |
| `PROMETHEUS_URL` | `https://prometheus.nrp-nautilus.io` | NRP Prometheus endpoint |
| `AMIE_SITE_NAME` | `NRP` | Site name for AMIE client |
| `AMIE_API_KEY` | `` | API key for AMIE client |
| `AMIE_URL` | `https://amieclient.xsede.org/v0.10/` | AMIE API base URL |
| `AMIE_PROCESSED_CLIENT_STATE` | `nrp-processed` | Client state set after successful ingestion |
| `AMIE_USAGE_URL` | `https://usage.xsede.org/api/v1` | AMIE usage API base URL |
| `AMIE_USAGE_INTERVAL_MINUTES` | `1440` | Usage export interval and usage record bucket size (default: once daily) |
| `AMIE_USAGE_GPU_CHARGE_FACTOR` | `1.0` | Multiplier applied to GPU usage when computing charge |
| `AMIE_USAGE_DEFAULT_USERNAME` | `nrp-system` | Fallback username for usage records when no login is mapped |
