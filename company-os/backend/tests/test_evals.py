"""The retrieval eval is a CI gate: kernel-corpus hit rate must not drop below
evals/retrieval/baseline.json. The second test proves the gate actually bites."""

import json

from app.kernel.evals import (
    EVALS_DIR,
    baseline,
    ingest_files,
    kernel_corpus_files,
    load_cases,
    run_retrieval_eval,
)
from app.kernel.memory.retriever import default_retriever
from app.kernel.tenancy import Principal


def _setup(make_workspace, db):
    w = make_workspace("evals")
    principal = Principal(user_id=w["user"].id, workspace_id=w["ws"].id, role="founder")
    assert ingest_files(db, principal, kernel_corpus_files()) >= 10
    db.commit()
    return w["ws"].id, load_cases(EVALS_DIR / "kernel_docs.jsonl")


def test_kernel_retrieval_meets_baseline(make_workspace, db):
    ws_id, cases = _setup(make_workspace, db)
    assert len(cases) >= 20
    result = run_retrieval_eval(db, ws_id, cases, k=3)
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    assert result.hit_rate >= baseline(), json.dumps(result.failures, indent=2, ensure_ascii=False)


def test_gate_fails_when_retrieval_breaks(make_workspace, db):
    ws_id, cases = _setup(make_workspace, db)

    class WorstFirst:
        """A deliberately broken retriever: returns the lowest-ranked matches."""

        def search(self, db, workspace_id, query, limit=5):
            return list(reversed(default_retriever().search(db, workspace_id, query, 20)))[:limit]

    broken = run_retrieval_eval(db, ws_id, cases, k=3, retriever=WorstFirst())
    assert broken.hit_rate < baseline()


def test_company_template_parses_to_zero_cases():
    assert load_cases(EVALS_DIR / "company_docs.jsonl") == []
