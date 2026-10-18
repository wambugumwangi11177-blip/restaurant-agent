"""
S6.1 — the M-Pesa statement comes in (docs/v2/SPEC.md §4 P6): `parsers/mpesa_csv.py` behind a parser interface, a fixture designed from public
format descriptions, models + migration 055, and /api/v1/owner/mpesa/{statement,statements}.

THE REAL EXPORT FORMAT IS UNKNOWN (SPEC Appendix B #1). These tests pin what the parser does with a statement SHAPED like the public
descriptions, and what it refuses to guess. They cannot say that a real statement parses; docs/v2/PROGRESS.md says a real sample is needed.

What this pins:
  * the parser reads a preamble, aliased headers, other column orders, several date formats, UTF-8 / BOM / Windows-1252, "KES 1,250";
  * Nairobi times become naive UTC, money becomes integer cents (never a float; "1e3", "NaN" and half-cents are refused);
  * a row it cannot read is LEFT OUT AND LISTED with its row number and why — failed payments, repeated receipts, totals, bad times;
  * a file that is not a statement, is empty, is too big, or is binary says so in the owner's words and stores nothing;
  * a second format is one class in PARSERS;
  * uploading is idempotent on M-Pesa's receipt number per restaurant, overlapping statements add only what is new, an upload can be undone;
  * owners, managers and controllers may; every other role 403, anonymous 401; another tenant's upload is a 404 and its payments never mix;
  * migration 055 is additive, idempotent, reversible, renders PostgreSQL DDL.
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

import auth
import models
from parsers import mpesa_csv
from parsers.mpesa_csv import MAX_BYTES, PARSERS, ParsedStatement, StatementError, parse_cents, parse_statement, parse_time

BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = BACKEND / "tests" / "fixtures" / "mpesa" / "statement_sample.csv"
API = "/api/v1/owner/mpesa"


def sample() -> bytes:
    return FIXTURE.read_bytes()


def csv_of(*rows: str, header: str = "Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance") -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


# ═════════════════════════════════════════════════════════════════════════════
# The parser, on the designed fixture
# ═════════════════════════════════════════════════════════════════════════════

def test_the_fixture_is_read_line_for_line():
    s = parse_statement(sample())
    assert [l.receipt for l in s.lines] == ["SJE4K2L9QA", "SJE4K2LAB7", "SJE4K2LC03", "SJE4K2LD55", "SJE4K2LF90", "SJE4K2LG44", "SJE4K2LH18", "SJE4K2LJ77"]
    first = s.lines[0]
    assert (first.paid_in_cents, first.withdrawn_cents, first.balance_cents, first.status) == (125_000, 0, 4_831_000, "Completed")
    assert first.details == "Customer Payment from 2547****1234 - JOHN KAMAU"
    supplier, charge = s.lines[5], s.lines[6]
    assert (supplier.paid_in_cents, supplier.withdrawn_cents) == (0, 800_000) and (charge.paid_in_cents, charge.withdrawn_cents) == (0, 3_500)


def test_times_are_nairobi_in_the_file_and_naive_utc_here():
    s = parse_statement(sample())
    assert s.lines[0].completed_at == datetime(2026, 10, 14, 9, 41, 7)            # 12:41:07 in Nairobi
    assert all(l.completed_at.tzinfo is None for l in s.lines)
    assert s.period == (datetime(2026, 10, 14, 9, 41, 7), datetime(2026, 10, 14, 15, 44, 19))


def test_what_the_preamble_said_is_kept():
    about = parse_statement(sample()).about
    assert about["short_code"] == "174379" and about["account_name"] == "Vibanda Restaurant - Till" and about["currency"] == "KES"


def test_rows_it_will_not_guess_at_are_listed_with_their_row_number_and_why():
    skipped = {s.row: s.reason for s in parse_statement(sample()).skipped}
    assert list(skipped) == [12, 17, 18, 20]
    assert "failed" in skipped[12] and "not completed" in skipped[12]
    assert "appears twice" in skipped[17] and "SJE4K2LJ77" in skipped[17]
    assert "is not one we can read" in skipped[18]
    assert "not a receipt number" in skipped[20]                                   # the Total row


def test_the_first_of_a_repeated_receipt_is_kept_even_when_the_case_differs():
    s = parse_statement(sample())
    assert sum(1 for l in s.lines if l.receipt == "SJE4K2LJ77") == 1


def test_a_blank_row_is_not_an_error():
    assert 19 not in {s.row for s in parse_statement(sample()).skipped}


# ═════════════════════════════════════════════════════════════════════════════
# What varies between exports is tolerated
# ═════════════════════════════════════════════════════════════════════════════

def test_no_preamble_and_a_different_column_order():
    raw = csv_of("14/10/2026 12:41,SJE4K2L9QA,Completed,\"1,250.00\",,Customer Payment", header="Completion Time,Receipt No,Transaction Status,Paid In,Withdrawn,Details")
    (line,) = parse_statement(raw).lines
    assert (line.receipt, line.paid_in_cents, line.completed_at) == ("SJE4K2L9QA", 125_000, datetime(2026, 10, 14, 9, 41))


@pytest.mark.parametrize("header", ["Receipt Number,Completed Time,Description,Status,Credit,Debit,Running Balance",
                                    "receipt no.,COMPLETION TIME,details,transaction status,paid in,withdrawn,balance",
                                    "Transaction ID,Transaction Date,Details,Status,Money In,Money Out,Balance"])
def test_other_words_for_the_same_columns(header):
    (line,) = parse_statement(csv_of("SJE4K2L9QA,2026-10-14 12:41:07,Customer Payment,Completed,300.00,,1000.00", header=header)).lines
    assert (line.receipt, line.paid_in_cents, line.balance_cents) == ("SJE4K2L9QA", 30_000, 100_000)


@pytest.mark.parametrize("text,expected", [
    ("2026-10-14 12:41:07", datetime(2026, 10, 14, 9, 41, 7)), ("2026-10-14 12:41", datetime(2026, 10, 14, 9, 41)),
    ("14-10-2026 12:41:07", datetime(2026, 10, 14, 9, 41, 7)), ("14/10/2026 12:41:07", datetime(2026, 10, 14, 9, 41, 7)),
    ("14/10/2026 12:41", datetime(2026, 10, 14, 9, 41)), ("14-Oct-2026 12:41:07", datetime(2026, 10, 14, 9, 41, 7)),
    ("14/10/2026 01:05:00 PM", datetime(2026, 10, 14, 10, 5)), ("2026-10-14T12:41:07", datetime(2026, 10, 14, 9, 41, 7)),
    ("2026-10-14 00:30:00", datetime(2026, 10, 13, 21, 30)),                                   # just after midnight in Nairobi is the evening before in UTC
])
def test_dates_as_the_statement_may_write_them(text, expected):
    assert parse_time(text) == expected


@pytest.mark.parametrize("text", ["", "yesterday", "2026-13-40 00:00:00", "12:41", "14.10.2026 12:41"])
def test_times_it_does_not_know_are_none_not_a_guess(text):
    assert parse_time(text) is None


def test_a_dd_mm_date_is_never_read_month_first():
    assert parse_time("03/04/2026 10:00:00") == datetime(2026, 4, 3, 7, 0)                    # 3 April, not 4 March


@pytest.mark.parametrize("text,cents", [("1,250.00", 125_000), ("KES 1,250", 125_000), ("Ksh. 40", 4_000), ("kshs 12.5", 1_250), ("-300", 30_000),
                                        ("0.07", 7), ("", 0), ("-", 0), ("  99.99 ", 9_999), ("1 250", 125_000)])
def test_money_is_integer_cents(text, cents):
    assert parse_cents(text) == cents and isinstance(parse_cents(text), int)


@pytest.mark.parametrize("text", ["1e3", "NaN", "inf", "12.345", "12.3.4", "abc", "1,2,3x", "٣٠٠"])
def test_money_it_cannot_be_sure_of_is_none(text):
    assert parse_cents(text) is None


def test_utf8_with_a_bom_and_windows_1252_both_read():
    row = "SJE4K2L9QA,2026-10-14 12:41:07,Café – lunch payment,Completed,300.00,,1000.00"
    body = csv_of(row)
    assert parse_statement(b"\xef\xbb\xbf" + body).lines[0].receipt == "SJE4K2L9QA"
    cp = ("Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance\n" + row.replace("–", "-") + "\n").encode("cp1252")
    assert "Café" in parse_statement(cp).lines[0].details


def test_extra_columns_and_short_rows_do_not_break_it():
    raw = csv_of("SJE4K2L9QA,2026-10-14 12:41:07,Customer Payment,Completed,300.00", "SJE4K2LAB7,2026-10-14 12:50:00,x,Completed,100.00,,500.00,Yes,extra,more",
                 header="Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance,Balance Confirmed,Reason Type,Other")
    s = parse_statement(raw)
    assert [l.paid_in_cents for l in s.lines] == [30_000, 10_000] and s.lines[0].balance_cents is None


def test_status_words_for_a_completed_payment():
    for word in ("Completed", "completed", "Complete", "Success", "Successful", ""):
        assert parse_statement(csv_of(f"SJE4K2L9QA,2026-10-14 12:41:07,x,{word},300.00,,")).lines, word
    for word in ("Failed", "Reversed", "Pending", "Cancelled"):
        s = parse_statement(csv_of(f"SJE4K2L9QA,2026-10-14 12:41:07,x,{word},300.00,,"))
        assert not s.lines and word.lower() in s.skipped[0].reason


# ═════════════════════════════════════════════════════════════════════════════
# What it refuses to guess
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("row,why", [
    ("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,,", "no amount"),
    ("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,0.00,0.00,", "no amount"),
    ("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,300.00,200.00,", "both money in and money out"),
    ("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,300.005,,", "not a number of shillings and cents"),
    ("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,three hundred,,", "not a number of shillings and cents"),
    ("AB1,2026-10-14 12:41:07,x,Completed,300.00,,", "not a receipt number"),
    (",2026-10-14 12:41:07,x,Completed,300.00,,", "no receipt number"),
    ("SJE4K2L9QA,soon,x,Completed,300.00,,", "is not one we can read"),
])
def test_a_row_that_cannot_be_trusted_is_left_out_and_says_why(row, why):
    s = parse_statement(csv_of(row))
    assert s.lines == [] and why in s.skipped[0].reason and s.skipped[0].row == 2


def test_a_negative_withdrawal_is_still_money_out():
    (line,) = parse_statement(csv_of("SJE4K2L9QA,2026-10-14 12:41:07,Supplier,Completed,,-8000.00,")).lines
    assert (line.paid_in_cents, line.withdrawn_cents) == (0, 800_000)


@pytest.mark.parametrize("raw,fragment", [
    (b"", "empty"), (b"   \n \n", "empty"),
    (b"name,price\nChips,300\n", "does not look like an M-Pesa statement"),
    (b"Receipt No.,Completion Time\nSJE4K2L9QA,2026-10-14 12:41:07\n", "does not look like an M-Pesa statement"),          # no Paid In column
    (b"just some words", "does not look like an M-Pesa statement"),
    (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(256)) * 4, "could not be read as text"),
], ids=["empty", "blank", "wrong-columns", "no-paid-in", "words", "image"])
def test_a_file_that_is_not_a_statement_is_refused_in_the_owners_words(raw, fragment):
    with pytest.raises(StatementError) as err:
        parse_statement(raw)
    assert fragment in str(err.value)
    assert not any(w in str(err.value).lower() for w in ("traceback", "csv.error", "decode", "exception", "none"))


def test_a_csv_the_reader_gives_up_on_is_refused_in_words():
    """The csv module refuses a single field over 128 KB. That is not a statement; it must not surface as a stack trace."""
    with pytest.raises(StatementError, match="not a well-formed CSV"):
        parse_statement(b"Receipt No.,Completion Time,Paid In\nSJE4K2L9QA,2026-10-14 12:41:07," + b"9" * 200_000 + b"\n")


def test_a_nul_byte_means_it_is_not_a_text_file():
    with pytest.raises(StatementError, match="could not be read as text"):
        parse_statement(b"Receipt No.,Completion Time,Paid In\n\x00\x00\x00")


def test_a_file_over_the_size_limit_is_refused():
    with pytest.raises(StatementError, match="larger than 5 MB"):
        parse_statement(b"x" * (MAX_BYTES + 1))


def test_a_statement_with_too_many_rows_is_refused():
    rows = [f"SJE{n:07d},2026-10-14 12:41:07,x,Completed,1.00,," for n in range(mpesa_csv.MAX_ROWS + 100)]
    with pytest.raises(StatementError, match="more than 20,000 rows"):
        parse_statement(csv_of(*rows))


def test_garbage_never_raises_anything_but_a_statement_error():
    import random
    rng = random.Random(61)
    for _ in range(200):
        blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 400)))
        try:
            parse_statement(blob)
        except StatementError:
            pass


def test_the_header_may_be_under_a_long_preamble_but_not_buried_forever():
    preamble = "\n".join(f"Note {n},x" for n in range(30))
    assert parse_statement((preamble + "\n").encode() + csv_of("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,300.00,,")).lines
    buried = "\n".join(f"Note {n},x" for n in range(80))
    with pytest.raises(StatementError):
        parse_statement((buried + "\n").encode() + csv_of("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,300.00,,"))


# ═════════════════════════════════════════════════════════════════════════════
# The interface: a second format is one class
# ═════════════════════════════════════════════════════════════════════════════

def test_the_csv_parser_is_registered_by_name_and_is_the_default():
    assert set(PARSERS) == {"mpesa_csv"} and PARSERS["mpesa_csv"].name == "mpesa_csv"
    assert parse_statement(sample()).parser == "mpesa_csv"


def test_an_unknown_format_is_refused_and_names_what_is_known():
    with pytest.raises(StatementError, match="mpesa_csv"):
        parse_statement(sample(), "mpesa_pdf")


def test_a_second_format_is_one_class(monkeypatch):
    class Tiny:
        name = "tiny"

        def parse(self, raw: bytes) -> ParsedStatement:
            return ParsedStatement(parser="tiny", lines=[mpesa_csv.StatementLine("TINY000001", datetime(2026, 10, 14), 100, 0, "", "Completed")])

    monkeypatch.setitem(PARSERS, "tiny", Tiny())
    assert parse_statement(b"anything", "tiny").lines[0].receipt == "TINY000001"


# ═════════════════════════════════════════════════════════════════════════════
# The endpoint
# ═════════════════════════════════════════════════════════════════════════════

def _tenant(db, suffix, *, staff_role=models.StaffRole.OWNER, role=models.Role.STAFF, restaurants=1):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db.add(tenant)
    db.flush()
    rests = []
    for n in range(restaurants):
        r = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}{n}", address="x")
        db.add(r)
        rests.append(r)
    user = models.User(tenant_id=tenant.id, email=f"u{suffix}@e.com", hashed_password=auth.get_password_hash("x"),
                       role=role, staff_role=staff_role, token_version=0)
    db.add(user)
    db.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return tenant, rests, user, {"Authorization": f"Bearer {token}"}


def _upload(client, headers, content=None, name="statement.csv"):
    return client.post(f"{API}/statement", headers=headers, files={"file": (name, sample() if content is None else content, "text/csv")})


def test_uploading_the_fixture_stores_its_payments_in_cents(client, db_session):
    _t, (r,), user, h = _tenant(db_session, "a")
    res = _upload(client, h)
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["new"], body["already_uploaded"], body["not_read_count"]) == (8, 0, 4)
    assert body["money_in_kes"] == 6_315.0 and body["money_out_kes"] == 8_035.0
    assert body["upload"]["filename"] == "statement.csv" and body["upload"]["lines"] == 8 and body["upload"]["uploaded_by"] == user.email
    assert body["about"]["short_code"] == "174379"
    rows = db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=r.id).order_by(models.MpesaStatementLine.completed_at).all()
    assert len(rows) == 8 and all(isinstance(x.paid_in_cents, int) and isinstance(x.withdrawn_cents, int) for x in rows)
    assert sum(x.paid_in_cents for x in rows) == 631_500 and sum(x.withdrawn_cents for x in rows) == 803_500


def test_the_unread_rows_are_in_the_answer_with_their_reasons(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    body = _upload(client, h).json()
    assert [n["row"] for n in body["not_read"]] == [12, 17, 18, 20] and all(n["reason"] for n in body["not_read"])


def test_uploading_the_same_file_again_adds_nothing_and_stores_no_empty_upload(client, db_session):
    _t, (r,), _u, h = _tenant(db_session, "a")
    _upload(client, h)
    again = _upload(client, h)
    assert again.status_code == 200 and again.json()["new"] == 0 and again.json()["already_uploaded"] == 8 and again.json()["upload"] is None
    assert db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=r.id).count() == 8
    assert db_session.query(models.MpesaStatementUpload).filter_by(restaurant_id=r.id).count() == 1


def test_an_overlapping_statement_adds_only_the_payments_that_are_new(client, db_session):
    _t, (r,), _u, h = _tenant(db_session, "a")
    _upload(client, h, csv_of("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,\"1,250.00\",,", "SJE4K2LAB7,2026-10-14 12:52:40,x,Completed,640.00,,"))
    second = _upload(client, h).json()
    assert (second["new"], second["already_uploaded"]) == (6, 2)
    assert db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=r.id).count() == 8
    assert [u.line_count for u in db_session.query(models.MpesaStatementUpload).order_by(models.MpesaStatementUpload.id)] == [2, 6]


def test_the_same_receipt_in_two_restaurants_is_two_payments(client, db_session):
    _ta, (ra,), _ua, ha = _tenant(db_session, "a")
    _tb, (rb,), _ub, hb = _tenant(db_session, "b")
    assert _upload(client, ha).json()["new"] == 8 and _upload(client, hb).json()["new"] == 8
    counts = {rid: db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=rid).count() for rid in (ra.id, rb.id)}
    assert counts == {ra.id: 8, rb.id: 8}


def test_listing_shows_uploads_newest_first_and_the_payments_on_file(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    _upload(client, h, csv_of("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,300.00,,"), name="first.csv")
    _upload(client, h, name="second.csv")
    body = client.get(f"{API}/statements", headers=h).json()
    assert [s["filename"] for s in body["statements"]] == ["second.csv", "first.csv"] and body["payments_on_file"] == 8
    assert body["statements"][0]["from"].endswith("+00:00") and body["statements"][0]["lines"] == 7


def test_deleting_an_upload_takes_its_payments_with_it_and_only_those(client, db_session):
    _t, (r,), _u, h = _tenant(db_session, "a")
    first = _upload(client, h, csv_of("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,300.00,,")).json()["upload"]["id"]
    second = _upload(client, h).json()["upload"]["id"]
    res = client.delete(f"{API}/statements/{second}", headers=h)
    assert res.status_code == 200 and res.json() == {"deleted": second, "payments_removed": 7}
    assert [l.receipt for l in db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=r.id)] == ["SJE4K2L9QA"]
    assert [u.id for u in db_session.query(models.MpesaStatementUpload).filter_by(restaurant_id=r.id)] == [first]
    assert _upload(client, h).json()["new"] == 7                                                   # and the undone payments can come back


def test_a_filename_is_only_a_name(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    assert _upload(client, h, name="..\\..\\etc\\passwd.csv").json()["upload"]["filename"] == "passwd.csv"


def test_a_filename_loses_control_characters_and_is_never_empty_or_long():
    from owner.mpesa_statement import clean_filename
    assert clean_filename("pass\x07wd\r\n.csv") == "passwd.csv"
    assert clean_filename("a/b/c.csv") == "c.csv" and clean_filename("") == "statement.csv" and clean_filename(None) == "statement.csv"
    assert clean_filename("\x00\x01") == "statement.csv" and len(clean_filename("x" * 400 + ".csv")) == 255


@pytest.mark.parametrize("content,status,fragment", [
    (b"", 422, "empty"), (b"name,price\nChips,300\n", 422, "does not look like an M-Pesa statement"),
    (b"x" * (MAX_BYTES + 5), 413, "larger than 5 MB"),
])
def test_a_bad_upload_is_refused_in_words_and_stores_nothing(client, db_session, content, status, fragment):
    _t, _r, _u, h = _tenant(db_session, "a")
    res = _upload(client, h, content)
    assert res.status_code == status and fragment in res.json()["detail"]
    assert db_session.query(models.MpesaStatementUpload).count() == 0 and db_session.query(models.MpesaStatementLine).count() == 0


def test_a_statement_bigger_than_the_json_limit_still_gets_through(client, db_session):
    """The API refuses a request body over 1 MB (middleware/body_limit.py) because it takes JSON; a statement is a file, and a month of
    a busy till is a few MB. Only this path is allowed more."""
    rows = [f"SJE{n:07d},2026-10-14 12:41:07,Customer Payment from 2547****1234 - SOMEBODY WITH A LONGER NAME,Completed,{1 + n % 900}.00,,{n}.00" for n in range(12_000)]
    raw = csv_of(*rows)
    assert 1_048_576 < len(raw) < MAX_BYTES
    _t, (r,), _u, h = _tenant(db_session, "a")
    res = _upload(client, h, raw)
    assert res.status_code == 201 and res.json()["new"] == 12_000
    assert db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=r.id).count() == 12_000


def test_the_larger_allowance_is_for_the_statement_path_alone(client, db_session):
    from middleware.body_limit import LARGER_BODY_PATHS, MAX_REQUEST_BODY_BYTES, limit_for
    assert set(LARGER_BODY_PATHS) == {f"{API}/statement"} and limit_for(f"{API}/statement") > MAX_BYTES        # room for the file and the form's framing
    assert limit_for(f"{API}/statements") == limit_for("/api/v1/orders") == MAX_REQUEST_BODY_BYTES
    _t, _r, _u, h = _tenant(db_session, "a")
    assert client.post("/api/v1/owner/money/expenses", headers=h, content=b"x" * (MAX_REQUEST_BODY_BYTES + 10)).status_code == 413


def test_a_body_beyond_even_the_statement_allowance_is_refused_before_it_is_read(client, db_session):
    from middleware.body_limit import limit_for
    _t, _r, _u, h = _tenant(db_session, "a")
    res = _upload(client, h, b"x" * (limit_for(f"{API}/statement") + 10))
    assert res.status_code == 413 and res.json()["detail"] == "Request body too large"


def test_a_request_without_a_file_is_a_422(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    assert client.post(f"{API}/statement", headers=h).status_code == 422
    assert client.post(f"{API}/statement", headers=h, data={"file": "not a file"}).status_code == 422


@pytest.mark.parametrize("staff_role", [models.StaffRole.SUPERVISOR, models.StaffRole.STOCKKEEPER, models.StaffRole.KITCHEN, models.StaffRole.WAITER])
def test_other_staff_roles_cannot_touch_the_statement(client, db_session, staff_role):
    _t, _r, _o, owner_h = _tenant(db_session, "own")
    uid = _upload(client, owner_h).json()["upload"]["id"]
    _t2, _r2, _u, h = _tenant(db_session, f"s{staff_role.value}", staff_role=staff_role)
    assert _upload(client, h).status_code == 403
    assert client.get(f"{API}/statements", headers=h).status_code == 403
    assert client.delete(f"{API}/statements/{uid}", headers=h).status_code == 403
    assert db_session.query(models.MpesaStatementUpload).count() == 1


@pytest.mark.parametrize("staff_role", [models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.CONTROLLER])
def test_owner_manager_and_controller_the_accountant_may(client, db_session, staff_role):
    _t, _r, _u, h = _tenant(db_session, f"s{staff_role.value}", staff_role=staff_role)
    assert _upload(client, h).status_code == 201 and client.get(f"{API}/statements", headers=h).status_code == 200


def test_anonymous_callers_are_401(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    uid = _upload(client, h).json()["upload"]["id"]
    assert client.post(f"{API}/statement", files={"file": ("s.csv", sample(), "text/csv")}).status_code == 401
    assert client.get(f"{API}/statements").status_code == 401 and client.delete(f"{API}/statements/{uid}").status_code == 401


def test_another_tenants_upload_is_a_404_and_its_payments_never_appear(client, db_session):
    _ta, (ra,), _ua, ha = _tenant(db_session, "a")
    _tb, (rb,), _ub, hb = _tenant(db_session, "b")
    uid = _upload(client, ha).json()["upload"]["id"]
    _upload(client, hb, csv_of("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,300.00,,"), name="b.csv")
    assert client.delete(f"{API}/statements/{uid}", headers=hb).status_code == 404
    mine = client.get(f"{API}/statements", headers=hb).json()
    assert [s["filename"] for s in mine["statements"]] == ["b.csv"] and mine["payments_on_file"] == 1
    assert db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=ra.id).count() == 8            # B's delete touched nothing of A's


def test_forging_the_active_restaurant_does_not_cross_the_tenant_boundary(client, db_session):
    _ta, (ra,), _ua, ha = _tenant(db_session, "a")
    _tb, (rb,), ub, hb = _tenant(db_session, "b")
    _upload(client, ha)
    ub.active_restaurant_id = ra.id
    db_session.commit()
    assert client.get(f"{API}/statements", headers=hb).json()["payments_on_file"] == 0
    assert _upload(client, hb, csv_of("SJE4K2L9QA,2026-10-14 12:41:07,x,Completed,300.00,,")).status_code == 201
    assert {l.restaurant_id for l in db_session.query(models.MpesaStatementLine)} == {ra.id, rb.id}
    assert db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=rb.id).count() == 1


def test_each_branch_of_a_chain_has_its_own_statement(client, db_session):
    _t, (r1, r2), user, h = _tenant(db_session, "chain", restaurants=2)
    user.active_restaurant_id = r1.id
    db_session.commit()
    _upload(client, h)
    user.active_restaurant_id = r2.id
    db_session.commit()
    assert client.get(f"{API}/statements", headers=h).json()["payments_on_file"] == 0
    assert _upload(client, h).json()["new"] == 8                                           # the same receipts are new at the other branch
    assert {rid: db_session.query(models.MpesaStatementLine).filter_by(restaurant_id=rid).count() for rid in (r1.id, r2.id)} == {r1.id: 8, r2.id: 8}


def test_the_statement_api_is_inside_the_observer_mode_boundary():
    from observer_mode import is_blocked_request
    for method, path in (("POST", f"{API}/statement"), ("GET", f"{API}/statements"), ("DELETE", f"{API}/statements/1")):
        assert is_blocked_request(method, path), path


# ═════════════════════════════════════════════════════════════════════════════
# Migration 055
# ═════════════════════════════════════════════════════════════════════════════

TABLES = ("mpesa_statement_uploads", "mpesa_statement_lines")


def _load_migration():
    import importlib.util
    path = BACKEND / "alembic" / "versions" / "055_add_mpesa_statements.py"
    spec = importlib.util.spec_from_file_location("migration_055", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(connection, fn_name):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    module = _load_migration()
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, fn_name)()


def test_migration_055_follows_054_and_alembic_has_one_head():
    module = _load_migration()
    assert module.down_revision == "054_notification_push_held"
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1 and module.revision in {r.revision for r in script.walk_revisions()}


def test_migration_055_creates_exactly_the_model_columns_and_is_reversible_and_idempotent(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    models.Base.metadata.create_all(engine, tables=[models.Tenant.__table__, models.Restaurant.__table__, models.User.__table__])
    with engine.begin() as conn:
        _run_migration(conn, "upgrade")
        inspector = sa.inspect(conn)
        assert set(TABLES) <= set(inspector.get_table_names())
        for model in (models.MpesaStatementUpload, models.MpesaStatementLine):
            assert {c["name"] for c in inspector.get_columns(model.__tablename__)} == {c.name for c in model.__table__.columns}, model.__tablename__
        _run_migration(conn, "upgrade")                                  # create_all() already ran in production: must not raise
        _run_migration(conn, "downgrade")
        assert not set(TABLES) & set(sa.inspect(conn).get_table_names())
        _run_migration(conn, "downgrade")
        _run_migration(conn, "upgrade")
        assert set(TABLES) <= set(sa.inspect(conn).get_table_names())


def test_migration_055_renders_postgresql_ddl_offline():
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg2://offline:offline@localhost:5432/offline", "SECRET_KEY": "x"}
    up = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "054_notification_push_held:055_mpesa_statements", "--sql"],
                        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert up.returncode == 0, up.stderr[-1500:]
    for table in TABLES:
        assert f"CREATE TABLE {table}" in up.stdout, table
    assert "paid_in_cents INTEGER NOT NULL" in up.stdout and "uq_mpesa_lines_restaurant_receipt" in up.stdout and "DROP" not in up.stdout
    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "055_mpesa_statements:054_notification_push_held", "--sql"],
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert down.returncode == 0, down.stderr[-1500:]
    assert down.stdout.index("DROP TABLE mpesa_statement_lines") < down.stdout.index("DROP TABLE mpesa_statement_uploads")      # children first
