"""Home, Money, and Ask must agree on today's sales."""
import auth
import models
from tests.factories import seed_owner
from time_utils import utcnow


def _token(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': user.token_version or 0})}"}


def test_home_money_and_ask_today_sales_match(client, db_session):
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven", email="today-match@eleven.leviii")
    now = utcnow()
    for i, total in enumerate((12000, 18500, 24000, 8900, 16200)):
        db_session.add(
            models.Order(
                restaurant_id=restaurant.id,
                total=total,
                is_paid=True,
                status=models.OrderStatus.SERVED,
                payment_method=models.PaymentMethod.MPESA,
                created_at=now,
            )
        )
    db_session.commit()
    headers = _token(owner)
    home = client.get("/api/v1/eleven/home/today", headers=headers).json()
    money = client.get("/api/v1/eleven/money/today", headers=headers).json()
    ask = client.get("/api/v1/ai/ask", params={"question": "How are sales today?"}, headers=headers).json()
    assert home["sales_kes"] == money["sales_kes"]
    assert home["tickets"] == money["tickets"]
    assert home["tickets"] == 5
    data = ask.get("data", {})
    assert data.get("sales_kes") == home["sales_kes"]
    assert data.get("tickets") == home["tickets"]
    finding = ask.get("finding", "")
    assert "KES" in finding
    assert "KSh" not in finding