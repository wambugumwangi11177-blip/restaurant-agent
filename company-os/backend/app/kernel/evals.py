"""
app/kernel/evals.py
───────────────────
Retrieval evaluation: does memory search put a correct source in the top k?

A case is one JSON line:
  {"id": "...", "question": "...",
   "expect": [{"title": "<document title>", "heading": "<optional heading substring>"}, ...]}
A case passes when any of the top-k citations matches any `expect` entry
(several sources can legitimately answer one question).

Deterministic and free, so it gates CI on every push. Answer-quality evals that
call an LLM are a separate, paid, on-demand step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.kernel.memory.retriever import Citation, Retriever, default_retriever
from app.kernel.memory.service import ingest_text
from app.kernel.tenancy import Principal

COMPANY_OS_ROOT = Path(__file__).resolve().parents[3]
EVALS_DIR = COMPANY_OS_ROOT / "evals" / "retrieval"


@dataclass
class EvalResult:
    total: int
    hits: int
    k: int
    failures: list[dict] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return round(self.hits / self.total, 4) if self.total else 0.0

    def as_dict(self) -> dict:
        return {"total": self.total, "hits": self.hits, "k": self.k, "hit_rate": self.hit_rate, "failures": self.failures}


def load_cases(path: Path) -> list[dict]:
    cases = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        case = json.loads(line)
        if not case.get("question") or not case.get("expect"):
            raise ValueError(f"{path}:{n}: each case needs 'question' and a non-empty 'expect' list")
        cases.append(case)
    return cases


def doc_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def kernel_corpus_files() -> list[Path]:
    """The OS's own directives and ADRs — real documents, versioned with the code."""
    files = sorted((COMPANY_OS_ROOT / "directives").rglob("*.md"))
    files += sorted((COMPANY_OS_ROOT / "docs" / "adr").glob("0*.md"))
    return files


def ingest_files(db: Session, principal: Principal, files: list[Path]) -> int:
    n = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        _, created = ingest_text(db, principal, doc_title(text, f.stem), text,
                                 source=str(f.relative_to(COMPANY_OS_ROOT)) if f.is_relative_to(COMPANY_OS_ROOT) else f.name)
        n += int(created)
    return n


def _matches(c: Citation, expect: dict) -> bool:
    if c.document_title != expect["title"]:
        return False
    if "heading_exact" in expect:  # a specific section, e.g. a document's untitled top section
        return c.heading == expect["heading_exact"]
    heading = expect.get("heading")
    return heading is None or heading.lower() in c.heading.lower()


def run_retrieval_eval(db: Session, workspace_id: int, cases: list[dict], k: int = 3,
                       retriever: Retriever | None = None) -> EvalResult:
    retriever = retriever or default_retriever()
    result = EvalResult(total=len(cases), hits=0, k=k)
    for case in cases:
        top = retriever.search(db, workspace_id, case["question"], k)
        if any(_matches(c, e) for c in top for e in case["expect"]):
            result.hits += 1
        else:
            result.failures.append({
                "id": case.get("id"), "question": case["question"],
                "got": [f"{c.document_title} › {c.heading.split(' › ', 1)[-1]}" for c in top],
            })
    return result


def baseline() -> float:
    return float(json.loads((EVALS_DIR / "baseline.json").read_text())["min_hit_rate"])
