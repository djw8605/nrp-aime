@AGENTS.md

---

## Claude Code — Specific Notes

### Development branch
All changes go to the branch specified at session start (usually `claude/<slug>`). Never push to `main` without explicit instruction.

### Tool guidance
- Prefer `Edit` over `Write` for existing files — it keeps diffs reviewable.
- Use `Glob` / `Grep` for targeted searches; spawn an `Explore` subagent only when a search needs multiple rounds.
- Run `python -m pytest tests/ -v --tb=short` from `backend/` after any model or service change.
- After adding a model field, always run `alembic revision --autogenerate` and read the generated file before committing — autogenerate sometimes misses nullable changes or produces no-op migrations.

### Gotchas
- `amieclient` must be installed `--no-deps` (see Dockerfile and CI). Don't add it to `requirements.txt` with deps.
- `provisioning_state` is a legacy compatibility column; always set `lifecycle_state` as the primary state.
- SQLite (used in tests) doesn't support `ALTER COLUMN` — keep migrations `op.add_column` / `op.drop_column` only; never rename columns in a single step.
- `AUTH_DEV_BYPASS=true` skips admin auth in dev. It is set in `docker-compose.yml` — do not commit it to K8s config.
- `[skip deploy]` in the commit message prevents the build-and-deploy workflow from firing.
- **`User.remote_site_login` stores the CILogon subject ID** (not an HPC username). `ProjectUser.remote_site_login` stores the actual AMIE/HPC site login. Do not confuse them.
- Every login NRP sends to AMIE — `UserRemoteSiteLogin` (notify_account_create), `PiRemoteSiteLogin` (notify_project_create) and GPU usage `Username` — is `amie_login(...)` (last 30 chars, `services/aime/logins.py`; AMIE's `system_accounts.username` is varchar(30)). Always use the helper so account creation and usage send the same identifier; the stored `remote_site_login` values stay the full CILogon URL.
- GPU usage for ACCESS export comes from the **NRP accounting public API** (`services/nrp_accounting/client.py`), not Prometheus or a direct ClickHouse connection. Only `pnrp.sdsc.access-ci.org` allocations are exported; the ledger is `gpu_usage_records`. Usage is POSTed through `amieclient.UsageClient` (adapter: `services/aime/usage_api.py`). amieclient must be installed `--no-deps` from the pinned fork `djw8605/amieclient@1700828` (see Dockerfile/CI); PyPI 0.6.1 sends `ParentRecordID: [null]` on Compute records and lacks `UsageClient.loaded()`. Switch back to PyPI once upstream (xsede/amieclient#35) releases.

### Personal overrides
Put per-developer notes, local paths, and experimental flags in `CLAUDE.local.md` (gitignored).
