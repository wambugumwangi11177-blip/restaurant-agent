"""Alembic must have exactly one head.

Two unmerged branches each added a migration numbered 050 on top of 049
(050_creative_takes, and 050_add_reporting_facts on
claude/agent-different-work-ppl204). Merging both leaves two heads, and the
container command `alembic upgrade head && gunicorn ...` (backend/Dockerfile)
then fails before the app starts. This turns that into a red test run instead
of a backend that will not boot: renumber the later migration onto the earlier.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_a_single_head():
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, (
        f"multiple alembic heads {sorted(heads)}: point the newer migration's "
        "down_revision at the other one and renumber it")
