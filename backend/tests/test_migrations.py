"""Tests for Alembic migration chain integrity."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _alembic_config() -> Config:
    """Return an Alembic Config pointed at the backend migrations."""
    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    return cfg


class TestMigrationChain:
    """Verify the Alembic revision graph is linear and consistent."""

    def test_single_head(self):
        """There must be exactly one head revision (no branching)."""
        scripts = ScriptDirectory.from_config(_alembic_config())
        heads = scripts.get_heads()
        assert len(heads) == 1, (
            f"Expected 1 Alembic head, found {len(heads)}: {heads}"
        )

    def test_no_duplicate_revisions(self):
        """Every revision identifier must be unique."""
        scripts = ScriptDirectory.from_config(_alembic_config())
        seen = {}
        for script in scripts.walk_revisions():
            assert script.revision not in seen, (
                f"Duplicate revision ID: {script.revision}"
            )
            seen[script.revision] = script.path

    def test_chain_is_linear(self):
        """Walk from head to base — every revision should have at most one down_revision."""
        scripts = ScriptDirectory.from_config(_alembic_config())
        for script in scripts.walk_revisions():
            down = script.down_revision
            if down is not None and not isinstance(down, str):
                # down_revision is a tuple for branch merges
                assert len(down) <= 1, (
                    f"Revision {script.revision} has multiple down_revisions: {down}. "
                    "Merge migrations are not expected in this project."
                )

    def test_all_revisions_parseable(self):
        """Every revision file must be importable by Alembic."""
        scripts = ScriptDirectory.from_config(_alembic_config())
        revisions = list(scripts.walk_revisions())
        assert len(revisions) > 0, "No migration revisions found"
