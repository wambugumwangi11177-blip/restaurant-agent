"""Deterministic source metrics; vendor status semantics are explicit inputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from integration.source_contract import Sale, Tender


@dataclass(frozen=True)
class MetricRules:
    """Approved source status semantics, supplied only after source mapping."""
    included_sale_statuses: frozenset[str]
    included_tender_statuses: frozenset[str]

    def __post_init__(self) -> None:
        if not self.included_sale_statuses or not self.included_tender_statuses:
            raise ValueError("metric rules require explicit sale and tender statuses")


@dataclass(frozen=True)
class MoneySummary:
    sales_minor: int
    bill_count: int
    average_bill_minor: int | None
    collections_minor: int


def summarize_money(sales: Iterable[Sale], tenders: Iterable[Tender], rules: MetricRules) -> MoneySummary:
    """Sum only explicitly approved records; no float arithmetic or inferred refunds."""
    valid_sales = [sale for sale in sales if sale.status in rules.included_sale_statuses]
    sales_minor = sum(sale.amount_minor for sale in valid_sales)
    collections_minor = sum(tender.amount_minor for tender in tenders if tender.status in rules.included_tender_statuses)
    bill_count = len(valid_sales)
    return MoneySummary(
        sales_minor=sales_minor,
        bill_count=bill_count,
        average_bill_minor=(sales_minor // bill_count) if bill_count else None,
        collections_minor=collections_minor,
    )
