from datetime import datetime

from integration.metrics import MetricRules, summarize_money
from integration.source_contract import Sale, Tender


def test_money_metrics_use_integer_minor_units_and_explicit_statuses():
    now = datetime(2026, 9, 15, 10)
    sales = [
        Sale("a", "r", now, 1001, "closed"),
        Sale("b", "r", now, 999, "void"),
        Sale("c", "r", now, 1002, "closed"),
    ]
    tenders = [Tender("t1", "a", now, 1001, "cash", "posted"), Tender("t2", "b", now, 999, "cash", "void")]
    result = summarize_money(sales, tenders, MetricRules(frozenset({"closed"}), frozenset({"posted"})))
    assert result.sales_minor == 2003
    assert result.bill_count == 2
    assert result.average_bill_minor == 1001
    assert result.collections_minor == 1001
