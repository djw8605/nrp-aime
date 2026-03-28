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

### Personal overrides
Put per-developer notes, local paths, and experimental flags in `CLAUDE.local.md` (gitignored).
