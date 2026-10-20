"""
backend/parsers/mpesa_csv.py — an M-Pesa business statement (a CSV export) into the payments it lists (docs/v2/SPEC.md §4, sprint S6.1).

THE REAL EXPORT FORMAT IS NOT KNOWN. This parser was designed against public descriptions of the Safaricom M-PESA for Business
"transaction report" (a few lines about the till or paybill, then a header row, then one row per transaction:
`Receipt No., Completion Time, Initiation Time, Details, Transaction Status, Paid In, Withdrawn, Balance, …`) and a fixture written
from them (`tests/fixtures/mpesa/`). It is deliberately tolerant about what varies between exports and strict about what the matching
depends on:

  tolerant   a preamble before the header · header names in other words ("Receipt Number", "Credit") · other column order and extra
             columns · UTF-8 with or without a BOM, or Windows-1252 · several date formats · amounts as "1,250.00" or "KES 1,250"
  strict     a row needs a receipt number, a completion time, a status of "Completed" and an amount; one that does not is NOT guessed
             at: it is left out and listed, with its row number and why, so the owner sees what was not read.

Times in the statement are Nairobi time; they are stored as naive UTC like every other timestamp. Money is integer cents.
A real sample is needed before this is trusted on a real till (docs/v2/PROGRESS.md says so, and SPEC Appendix B #1).

The parser is behind an interface (`StatementParser`): a second format is one more class registered in PARSERS, nothing else changes.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from time_utils import EAT_OFFSET

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000
DEFAULT_FORMAT = "mpesa_csv"


class StatementError(ValueError):
    """The file cannot be read as a statement at all. The message is written for the owner."""


@dataclass(frozen=True)
class StatementLine:
    receipt: str
    completed_at: datetime            # naive UTC
    paid_in_cents: int                # money that came in (a customer paid the till)
    withdrawn_cents: int              # money that went out
    details: str
    status: str
    balance_cents: int | None = None


@dataclass(frozen=True)
class SkippedRow:
    row: int                          # the row number in the file, 1-based, as a spreadsheet shows it
    reason: str


@dataclass
class ParsedStatement:
    parser: str
    lines: list[StatementLine] = field(default_factory=list)
    skipped: list[SkippedRow] = field(default_factory=list)
    about: dict[str, str] = field(default_factory=dict)      # what the preamble said: short code, account name, period

    @property
    def period(self) -> tuple[datetime, datetime] | None:
        if not self.lines:
            return None
        times = [line.completed_at for line in self.lines]
        return min(times), max(times)


class StatementParser(Protocol):
    name: str

    def parse(self, raw: bytes) -> ParsedStatement: ...


# ── the CSV parser ───────────────────────────────────────────────────────────

_ALIASES = {
    "receipt": {"receipt no", "receipt number", "receipt", "transaction id", "transaction code", "trans id", "mpesa receipt", "receipt id"},
    "completed": {"completion time", "completed time", "completion date", "transaction time", "transaction date", "date time", "time", "date"},
    "details": {"details", "description", "transaction details"},
    "status": {"transaction status", "status"},
    "paid_in": {"paid in", "credit", "money in", "amount in"},
    "withdrawn": {"withdrawn", "debit", "money out", "amount out", "paid out"},
    "balance": {"balance", "running balance"},
}
_REQUIRED = ("receipt", "completed", "paid_in")
_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
    "%d-%b-%Y %H:%M:%S", "%d %b %Y %H:%M:%S", "%d/%m/%Y %I:%M:%S %p", "%d-%m-%Y %I:%M:%S %p",
)
_RECEIPT = re.compile(r"^[A-Za-z0-9]{6,20}$")
_MONEY_NOISE = re.compile(r"(?i)kshs?\.?|kes|[,\s]")
_MONEY = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")                   # plain digits only: no exponents, no NaN
_PREAMBLE_KEYS = {"account name": "account_name", "short code": "short_code", "shortcode": "short_code", "till number": "short_code",
                  "paybill": "short_code", "account type": "account_type", "statement period": "period", "currency": "currency"}


def _norm(cell: str) -> str:
    return re.sub(r"\s+", " ", (cell or "").strip().strip(".:").lower())


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StatementError("This file could not be read as text. Export the statement from M-Pesa as a CSV file and upload that.")


def _columns(header: list[str]) -> dict[str, int] | None:
    found: dict[str, int] = {}
    for i, cell in enumerate(header):
        name = _norm(cell)
        for key, aliases in _ALIASES.items():
            if name in aliases and key not in found:
                found[key] = i
    return found if all(k in found for k in _REQUIRED) else None


def parse_time(text: str) -> datetime | None:
    """A completion time as the statement writes it (Nairobi time) -> naive UTC. None when it is not a time we know."""
    text = (text or "").strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt) - EAT_OFFSET
        except ValueError:
            continue
    return None


def parse_cents(text: str) -> int | None:
    """"1,250.00" / "KES 1,250" / "-300" -> cents (always positive: the column says which way the money went). "" -> 0. None when not money."""
    cleaned = _MONEY_NOISE.sub("", text or "")
    if cleaned in ("", "-"):
        return 0
    if not _MONEY.fullmatch(cleaned):
        return None
    value = abs(Decimal(cleaned))
    cents = value * 100
    return int(cents) if cents == cents.to_integral_value() else None


class MpesaCsvParser:
    name = "mpesa_csv"

    def parse(self, raw: bytes) -> ParsedStatement:
        if len(raw) > MAX_BYTES:
            raise StatementError(f"This file is larger than {MAX_BYTES // (1024 * 1024)} MB. Export a shorter period and upload that.")
        if not raw.strip():
            raise StatementError("This file is empty.")
        if b"\x00" in raw[:4096]:
            raise StatementError("This file could not be read as text. Export the statement from M-Pesa as a CSV file and upload that.")
        try:
            rows = list(csv.reader(io.StringIO(_decode(raw), newline="")))
        except csv.Error:
            raise StatementError("This file is not a well-formed CSV (a quote or a line break is in the wrong place). "
                                 "Export the statement from M-Pesa again and upload that.") from None
        if len(rows) > MAX_ROWS + 50:
            raise StatementError(f"This statement has more than {MAX_ROWS:,} rows. Export a shorter period and upload that.")
        about: dict[str, str] = {}
        header_at, columns = None, None
        for i, row in enumerate(rows[:60]):
            columns = _columns(row)
            if columns:
                header_at = i
                break
            if len(row) >= 2 and _norm(row[0]) in _PREAMBLE_KEYS and row[1].strip():
                about[_PREAMBLE_KEYS[_norm(row[0])]] = row[1].strip()
        if columns is None:
            raise StatementError("This does not look like an M-Pesa statement. It needs a header row with at least the receipt number, "
                                 "the completion time and the Paid In amount. Export the transaction report from M-Pesa as a CSV file.")
        out = ParsedStatement(parser=self.name, about=about)
        seen: set[str] = set()
        for offset, row in enumerate(rows[header_at + 1:], start=header_at + 2):
            if not any(cell.strip() for cell in row):
                continue
            skip = self._row(row, columns, seen)
            if isinstance(skip, str):
                out.skipped.append(SkippedRow(offset, skip))
            else:
                out.lines.append(skip)
        return out

    @staticmethod
    def _cell(row: list[str], columns: dict[str, int], key: str) -> str:
        i = columns.get(key)
        return row[i].strip() if i is not None and i < len(row) else ""

    def _row(self, row: list[str], columns: dict[str, int], seen: set[str]) -> StatementLine | str:
        receipt = self._cell(row, columns, "receipt").upper()
        if not receipt:
            return "no receipt number (a total or note, not a payment)"
        if not _RECEIPT.match(receipt):
            return f"{receipt!r} is not a receipt number"
        if receipt in seen:
            return f"receipt {receipt} appears twice in this file; the first one was kept"
        status = self._cell(row, columns, "status")
        if status and _norm(status) not in ("completed", "complete", "success", "successful"):
            return f"the payment is {status.lower()!r}, not completed"
        completed_at = parse_time(self._cell(row, columns, "completed"))
        if completed_at is None:
            return f"the time {self._cell(row, columns, 'completed')!r} is not one we can read"
        paid_in = parse_cents(self._cell(row, columns, "paid_in"))
        withdrawn = parse_cents(self._cell(row, columns, "withdrawn"))
        if paid_in is None or withdrawn is None:
            return "an amount is not a number of shillings and cents"
        if paid_in == 0 and withdrawn == 0:
            return "no amount"
        if paid_in and withdrawn:
            return "both money in and money out on one row"
        balance = parse_cents(self._cell(row, columns, "balance")) if self._cell(row, columns, "balance") else None
        seen.add(receipt)
        return StatementLine(receipt=receipt, completed_at=completed_at, paid_in_cents=paid_in, withdrawn_cents=withdrawn,
                             details=self._cell(row, columns, "details")[:500], status=status or "Completed", balance_cents=balance)


PARSERS: dict[str, StatementParser] = {MpesaCsvParser.name: MpesaCsvParser()}


def parse_statement(raw: bytes, fmt: str = DEFAULT_FORMAT) -> ParsedStatement:
    parser = PARSERS.get(fmt)
    if parser is None:
        raise StatementError(f"We cannot read statements in the format {fmt!r}. We can read: {', '.join(sorted(PARSERS))}.")
    return parser.parse(raw)
