"""Run the regression gate against disposable SQLite fixtures, without Windows fsync overhead.

Only pytest temporary files get the in-memory rollback journal. Foreign keys and transactions are unchanged;
this runner is not a crash-durability test. Never imports or changes a live database.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['APP_ENV']='development'
os.environ['FEATURE_AI_NARRATION']='true'  # grounding tests stub the provider; real providers below are all empty
for name in ('OPENAI_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','ANTHROPIC_API_KEY'):
    os.environ[name]=''
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine,'connect')
def disposable_sqlite(connection, record):
    if not isinstance(connection,sqlite3.Connection):
        return
    cursor=connection.cursor()
    filename=cursor.execute('PRAGMA database_list').fetchone()[2]
    # A fixture file has to be under pytest's own temporary directory; not merely any local SQLite file.
    if filename and Path(filename).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()) and any(p.startswith('pytest-') for p in Path(filename).parts):
        cursor.execute('PRAGMA synchronous=OFF')
        cursor.execute('PRAGMA journal_mode=MEMORY')
    cursor.close()

os.chdir(ROOT/'backend')
sys.path.insert(0,str(ROOT/'backend'))
import pytest
raise SystemExit(pytest.main(sys.argv[1:] or ['-q','--tb=short']))
