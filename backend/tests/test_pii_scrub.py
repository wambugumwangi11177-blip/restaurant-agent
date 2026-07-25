"""
PII scrubbing at the LLM boundary (P4, 2026-07-11).

Proves scrub_for_llm() redacts phones / M-Pesa codes / label-gated PIN & ID
digits, while leaving money and percentage figures intact so number-grounding
still works. See ai/pii_scrub.py.

Name-denylist coverage added 2026-07-25 (audit remediation, Tier 3 item 8):
scrub_for_llm() takes an optional known_names param, and
known_names_for_restaurant() builds one from this restaurant's own
Order/Reservation/StaffMember records — see that function's docstring for the
documented, accepted gap (a name never recorded anywhere can't be caught).
"""

import models
from ai.pii_scrub import scrub_for_llm, known_names_for_restaurant


def test_redacts_kenyan_phone_formats():
    for raw in ["0712345678", "+254712345678", "254712345678", "0112345678"]:
        out = scrub_for_llm(f"call the customer on {raw} today")
        assert raw not in out, raw
        assert "[phone]" in out


def test_redacts_mpesa_confirmation_code():
    out = scrub_for_llm("Payment QGR7H2K9P1 received")
    assert "QGR7H2K9P1" not in out
    assert "[mpesa-code]" in out


def test_redacts_pin_only_with_label():
    out = scrub_for_llm("my pin is 1234 ok")
    assert "1234" not in out
    assert "pin" in out.lower()
    assert "[redacted]" in out


def test_redacts_national_id_with_label():
    out = scrub_for_llm("ID number 12345678 for the record")
    assert "12345678" not in out
    assert "[redacted]" in out


def test_keeps_money_and_percentages():
    # These MUST survive — grounding.collect_payload_numbers runs after scrub and
    # the model needs to cite them.
    text = "Revenue was KES 45,000 today, up 12% from yesterday across 87 orders."
    out = scrub_for_llm(text)
    assert "45,000" in out
    assert "12%" in out
    assert "87" in out


def test_bare_large_number_not_treated_as_id():
    # No 'id'/'pin' label -> a bare 8-digit figure (could be cents) is untouched.
    out = scrub_for_llm("Total sales 12345678 cents this month")
    assert "12345678" in out


def test_safe_on_empty_and_non_string():
    assert scrub_for_llm("") == ""
    assert scrub_for_llm(None) is None


def test_idempotent():
    once = scrub_for_llm("reach them on 0712345678")
    twice = scrub_for_llm(once)
    assert once == twice


# ── Name denylist (present in DB -> redacted; absent -> passes through) ───────

def test_known_name_present_in_db_is_redacted():
    out = scrub_for_llm("Follow up with Jane Wanjiru tomorrow", known_names=["Jane Wanjiru"])
    assert "Jane Wanjiru" not in out
    assert "[name]" in out


def test_name_absent_from_denylist_passes_through_documented_gap():
    # The whole point of the denylist approach: a name never recorded
    # anywhere (e.g. only ever spoken in free-text chat) can't be caught.
    out = scrub_for_llm("Follow up with Jane Wanjiru tomorrow", known_names=["Someone Else"])
    assert "Jane Wanjiru" in out


def test_no_known_names_reproduces_prior_behaviour_exactly():
    text = "Call the customer on 0712345678 about their order"
    assert scrub_for_llm(text) == scrub_for_llm(text, known_names=None)
    assert scrub_for_llm(text) == scrub_for_llm(text, known_names=[])


def test_longer_name_redacted_as_one_unit_not_fragmented():
    out = scrub_for_llm("John Doe called about his order", known_names=["John Doe", "John"])
    assert out == "[name] called about his order"


def test_short_names_under_two_chars_are_skipped():
    out = scrub_for_llm("A B stopped by", known_names=["A", "B"])
    assert out == "A B stopped by"


def test_known_names_for_restaurant_pulls_from_orders_reservations_and_staff(db_session):
    tenant = models.Tenant(name="PII Test Tenant")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="PII Test Restaurant")
    db_session.add(restaurant)
    db_session.commit()

    db_session.add(models.Order(restaurant_id=restaurant.id, customer_name="Order Customer", total=1000))
    db_session.add(models.Reservation(restaurant_id=restaurant.id, customer_name="Reservation Customer"))
    db_session.add(models.StaffMember(restaurant_id=restaurant.id, name="Staff Person", is_active=True))
    # A different restaurant's data must never leak into this one's denylist.
    other_restaurant = models.Restaurant(tenant_id=tenant.id, name="Other Restaurant")
    db_session.add(other_restaurant)
    db_session.commit()
    db_session.add(models.Order(restaurant_id=other_restaurant.id, customer_name="Other Restaurant Customer", total=500))
    db_session.commit()

    names = known_names_for_restaurant(db_session, restaurant.id)

    assert "Order Customer" in names
    assert "Reservation Customer" in names
    assert "Staff Person" in names
    assert "Other Restaurant Customer" not in names
