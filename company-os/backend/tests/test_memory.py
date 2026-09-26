from app.kernel.memory.chunking import chunk_document

DOC = """# Company Handbook

Intro paragraph about the company.

## Pricing
Our standard plan costs KES 15,000 per month per location.

Discounts above 10% need founder approval.

## Support
Clients reach support on WhatsApp between 08:00 and 20:00 EAT.

### Escalation
Outages are escalated to the founder within 30 minutes.
"""


def test_chunks_carry_heading_paths_and_exact_offsets():
    chunks = chunk_document(DOC, "Company Handbook")
    headings = [c.heading for c in chunks]
    assert "Company Handbook › Pricing" in headings
    assert "Company Handbook › Support › Escalation" in headings
    for c in chunks:
        assert DOC[c.char_start:c.char_end].strip() == c.content


def test_long_sections_split_within_limit():
    text = "# T\n\n" + "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(30))
    chunks = chunk_document(text, "T", max_chars=500)
    assert len(chunks) > 5 and all(len(c.content) <= 500 for c in chunks)
    one_huge = chunk_document("x" * 3000, "Big", max_chars=1000)
    assert [len(c.content) for c in one_huge] == [1000, 1000, 1000]


def test_ingest_is_idempotent_and_search_cites(client, make_workspace):
    w = make_workspace("acme")
    first = client.post("/api/v1/memory/documents", headers=w["h"], json={"title": "Company Handbook", "content": DOC})
    again = client.post("/api/v1/memory/documents", headers=w["h"], json={"title": "Other name", "content": DOC})
    assert first.json()["created"] is True and again.json()["created"] is False
    assert first.json()["id"] == again.json()["id"]

    r = client.get("/api/v1/memory/search", headers=w["h"], params={"q": "how fast are outages escalated?"}).json()
    top = r["results"][0]
    assert top["heading"] == "Company Handbook › Support › Escalation"
    assert "«" in top["snippet"]  # highlighted match
    r = client.get("/api/v1/memory/search", headers=w["h"], params={"q": "what does the plan cost"}).json()
    assert r["results"][0]["heading"] == "Company Handbook › Pricing"


def test_search_handles_stopword_and_symbol_queries(client, make_workspace):
    w = make_workspace("acme")
    client.post("/api/v1/memory/documents", headers=w["h"], json={"title": "H", "content": DOC})
    for q in ("the and of", "':|&!()", "a"):
        r = client.get("/api/v1/memory/search", headers=w["h"], params={"q": q})
        assert r.status_code == 200 and r.json()["results"] == []


def test_upload_and_delete(client, make_workspace):
    w = make_workspace("acme")
    up = client.post("/api/v1/memory/documents/upload", headers=w["h"],
                     files={"file": ("ops-runbook.md", b"# Runbook\nRestart the worker with care.", "text/markdown")})
    assert up.status_code == 201 and up.json()["title"] == "ops-runbook"
    pdf = client.post("/api/v1/memory/documents/upload", headers=w["h"],
                      files={"file": ("contract.pdf", b"%PDF-1.4", "application/pdf")})
    assert pdf.status_code == 415
    bad = client.post("/api/v1/memory/documents/upload", headers=w["h"],
                      files={"file": ("x.txt", b"\xff\xfe\x00bad", "text/plain")})
    assert bad.status_code == 422
    docs = client.get("/api/v1/memory/documents", headers=w["h"]).json()
    assert docs[0]["chunks"] == 1
    assert client.delete(f"/api/v1/memory/documents/{up.json()['id']}", headers=w["h"]).status_code == 204
    assert client.get("/api/v1/memory/search", headers=w["h"], params={"q": "restart worker"}).json()["results"] == []


def test_advisor_can_search_but_not_ingest(client, make_workspace, add_member):
    w = make_workspace("acme")
    adv = add_member(w["h"], "advisor", "adv@acme.example.com")
    assert client.post("/api/v1/memory/documents", headers=adv, json={"title": "x", "content": "y"}).status_code == 403
    assert client.get("/api/v1/memory/search", headers=adv, params={"q": "y"}).status_code == 200
