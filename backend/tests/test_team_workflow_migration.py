import importlib.util
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_workflow_migration_roundtrip_and_create_all_compatibility(tmp_path):
    path = Path(__file__).parents[1] / 'alembic/versions/060_team_workflows.py'
    spec = importlib.util.spec_from_file_location('workflow_migration', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = create_engine(f'sqlite:///{tmp_path / "migration.db"}')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE restaurants (id INTEGER PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade(); module.upgrade()
            assert set(inspect(conn).get_table_names()) == {'restaurants','users','team_workflows','team_workflow_events'}
            module.downgrade()
            assert set(inspect(conn).get_table_names()) == {'restaurants','users'}
            module.upgrade()
            assert 'request_key' in {c['name'] for c in inspect(conn).get_columns('team_workflows')}
    engine.dispose()
