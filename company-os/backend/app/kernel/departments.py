"""
app/kernel/departments.py
─────────────────────────
The registry departments plug into (ADR 0001). A department declares:
  - record types        (records.register_record_type)
  - reports             deterministic read-only views: {"title","summary","columns","rows"}
  - scheduled jobs      run by execution/run_jobs.py from cron, per workspace
  - agents / tools      (registry.register_agent / tools.register_tool)
Nothing here imports a department; departments import this.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.kernel.tenancy import Principal

ReportFn = Callable[[Session, Principal, dict], dict]
JobFn = Callable[[Session, int], str]


@dataclass(frozen=True)
class Report:
    key: str
    department: str
    label: str
    fn: ReportFn
    permission: str
    description: str = ""
    params: tuple[str, ...] = ()


@dataclass(frozen=True)
class Job:
    name: str
    department: str
    fn: JobFn
    schedule_hint: str  # documentation for the cron entry, e.g. "daily 07:00 Africa/Nairobi"


@dataclass(frozen=True)
class Department:
    key: str
    label: str
    order: int
    description: str
    permission: str  # minimum permission to see the department at all
    record_types: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()
    directive: str = ""
    extra: dict = field(default_factory=dict)


DEPARTMENTS: dict[str, Department] = {}
REPORTS: dict[str, Report] = {}
JOBS: dict[str, Job] = {}


def _put(registry: dict, key: str, item) -> None:
    existing = registry.get(key)
    if existing is not None and existing != item:
        raise ValueError(f"{key!r} already registered")
    registry[key] = item


def register_department(d: Department) -> None:
    _put(DEPARTMENTS, d.key, d)


def register_report(r: Report) -> None:
    _put(REPORTS, r.key, r)


def register_job(j: Job) -> None:
    _put(JOBS, j.name, j)


def table(title: str, summary: str, columns: list[str], rows: list[list]) -> dict:
    return {"title": title, "summary": summary, "columns": columns, "rows": rows}


# The founder's daily brief is owned by the Command Center, but every department
# can contribute lines to it without being imported by it.
BriefFn = Callable[[Session, int], list[str]]
BRIEF_SECTIONS: dict[str, tuple[str, BriefFn]] = {}


def register_brief_section(department: str, title: str, fn: BriefFn) -> None:
    BRIEF_SECTIONS[department] = (title, fn)


# Workspace settings a department reads (set by the founder via PUT /workspace/settings).
@dataclass(frozen=True)
class SettingSpec:
    key: str
    department: str
    description: str
    secret: bool = False  # masked on read (e.g. a private calendar URL)
    kind: str = "string"  # string | integer


SETTINGS: dict[str, SettingSpec] = {}


def register_setting(s: SettingSpec) -> None:
    _put(SETTINGS, s.key, s)
