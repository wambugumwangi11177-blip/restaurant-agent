"""Jack's store foundation: setup gate, recipe audit, money redaction, Eleven import."""
import io
from datetime import datetime

import pytest
from openpyxl import Workbook

import auth
import models
from money_visibility import MONEY_KEYS, money_keys_in
from time_utils import utcnow


def _token(user):
    return auth.create_access_token({"sub": user.email, "ver": user.token_version or 0})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _tenant(db, name, email, role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER, password="Ownerpass1"):
    tenant = models.Tenant(name=name)
    db.add(tenant)
    db.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=email,
        hashed_password=auth.get_password_hash(password),
        role=role,
        staff_role=staff_role,
        token_version=0,
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=name, address="Ngong Road")
    db.add(restaurant)
    db.commit()
    return tenant, user, restaurant


def _add_staff(db, tenant, restaurant, email, staff_role, password="TempPass1", must_change=False):
    user = models.User(
        tenant_id=tenant.id,
        email=email,
        hashed_password=auth.get_password_hash(password),
        role=models.Role.STAFF,
        staff_role=staff_role,
        token_version=0,
        is_active=True,
        must_change_password=must_change,
    )
    db.add(user)
    db.commit()
    db.add(models.StaffMember(
        restaurant_id=restaurant.id,
        user_id=user.id,
        name=email.split("@")[0],
        role_title=staff_role.value,
    ))
    if staff_role == models.StaffRole.STOCKKEEPER:
        db.add(models.StaffSetupProgress(
            user_id=user.id,
            restaurant_id=restaurant.id,
            updated_at=utcnow(),
            account_completed_at=None if must_change else utcnow(),
            recipes_completed_at=None if must_change else utcnow(),
        ))
    db.commit()
    return user


def _seed_money(db, restaurant, owner):
    item = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Rice",
        quantity=4,
        unit="kg",
        cost_per_unit=120,
        low_stock_threshold=1,
        expiry_days=30,
    )
    db.add(item)
    db.flush()
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Acme", contact_phone="", contact_email="", notes="")
    db.add(supplier)
    db.flush()
    dish = models.MenuItem(
        restaurant_id=restaurant.id, name="Pilau", category="Mains",
        price=80000, cost_price=20000, description="", is_available=True,
    )
    db.add(dish)
    db.flush()
    db.add(models.MenuIngredient(
        menu_item_id=dish.id, inventory_item_id=item.id,
        quantity_per_serving=0.2, yield_fraction=0.8, recipe_unit="kg",
        created_by_user_id=owner.id, created_at=utcnow(),
    ))
    db.add(models.PurchaseOrder(
        restaurant_id=restaurant.id, supplier_id=supplier.id, inventory_item_id=item.id,
        quantity_ordered=10, unit="kg", cost_per_unit=12000, total_cost=120000, status="SENT",
    ))
    order = models.Order(
        restaurant_id=restaurant.id, status=models.OrderStatus.PENDING,
        total=80000, customer_name="Sam",
    )
    db.add(order)
    db.flush()
    db.add(models.OrderItem(order_id=order.id, menu_item_id=dish.id, quantity=1, unit_price=80000))
    db.commit()
    return item, order


def test_owner_creates_jack_and_first_login_sets_password_and_pin(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "wambugu@eleven.leviii")
    created = client.post(
        "/api/v1/staff/",
        headers=_auth(_token(owner)),
        json={
            "name": "Jack",
            "role_title": "Storekeeper",
            "create_login": True,
            "email": "jack@eleven.leviii",
            "password": "TempPass1",
            "staff_role": "stockkeeper",
        },
    )
    assert created.status_code == 201, created.text
    login = client.post("/api/v1/auth/login", json={"email": "jack@eleven.leviii", "password": "TempPass1"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.json()["must_change_password"] is True
    assert me.json()["has_pin"] is False
    blocked = client.get("/api/v1/inventory/", headers=_auth(token))
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "password_change_required"
    weak_pin = client.post(
        "/api/v1/staff-setup/account",
        headers=_auth(token),
        json={"current_password": "TempPass1", "new_password": "NewPass2", "pin": "12345"},
    )
    assert weak_pin.status_code == 422
    saved = client.post(
        "/api/v1/staff-setup/account",
        headers=_auth(token),
        json={"current_password": "TempPass1", "new_password": "NewPass2", "pin": "1234"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["steps"][0]["state"] == "done"
    again = client.post("/api/v1/auth/login", json={"email": "jack@eleven.leviii", "password": "NewPass2"})
    assert again.status_code == 200
    jack = db_session.query(models.User).filter_by(email="jack@eleven.leviii").one()
    assert auth.verify_pin("1234", jack.hashed_pin)
    assert jack.must_change_password is False
    audit = db_session.query(models.StaffEntryAudit).filter_by(user_id=jack.id, action="account_ready").one()
    assert audit.created_at is not None
    assert "1234" not in audit.summary
    assert "1234" not in audit.detail_json


def test_recipe_lines_are_append_only_and_unlock_the_store(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-recipes@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-recipes@eleven.leviii", models.StaffRole.STOCKKEEPER, must_change=False)
    # Account is done, recipes are not, so the store stays on the recipe step.
    progress = db_session.query(models.StaffSetupProgress).filter_by(user_id=jack.id).one()
    progress.recipes_completed_at = None
    db_session.commit()
    headers = _auth(_token(jack))
    assert client.get("/api/v1/inventory/", headers=headers).status_code == 403
    saved = client.post(
        "/api/v1/store/recipes",
        headers=headers,
        json={
            "dish_name": "Sukuma",
            "ingredient_name": "Sukuma wiki",
            "quantity": 0.25,
            "unit": "kg",
            "yield_fraction": 0.8,
        },
    )
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert "price" not in body["dishes"][0]
    line = body["dishes"][0]["lines"][0]
    assert line["quantity"] == 0.25
    assert line["unit"] == "kg"
    assert line["yield_fraction"] == 0.8
    assert line["created_by_user_id"] == jack.id
    assert money_keys_in(body) == []
    too_soon = client.post("/api/v1/staff-setup/recipes", headers=headers)
    # A line exists, so this should succeed.
    assert too_soon.status_code == 200, too_soon.text
    assert too_soon.json()["app_unlocked"] is True
    opened = client.get("/api/v1/inventory/", headers=headers)
    assert opened.status_code == 200
    assert money_keys_in(opened.json()) == []
    audits = db_session.query(models.StaffEntryAudit).filter_by(user_id=jack.id).all()
    assert any(row.action == "recipe_line_added" for row in audits)
    row = audits[0]
    row.summary = "tampered"
    with pytest.raises(Exception, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_money_keys_absent_for_storekeeper_and_kitchen(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-money@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-money@eleven.leviii", models.StaffRole.STOCKKEEPER)
    cook = _add_staff(db_session, tenant, restaurant, "cook-money@eleven.leviii", models.StaffRole.KITCHEN)
    _seed_money(db_session, restaurant, owner)
    owner_headers = _auth(_token(owner))
    owner_stock = client.get("/api/v1/inventory/", headers=owner_headers)
    assert owner_stock.status_code == 200
    assert "cost_per_unit" in owner_stock.json()[0]

    calls = [
        ("stockkeeper", jack, "GET", "/api/v1/inventory/"),
        ("stockkeeper", jack, "GET", "/api/v1/menu/"),
        ("stockkeeper", jack, "GET", "/api/v1/menu/1/ingredients"),
        ("stockkeeper", jack, "GET", "/api/v1/purchase-orders/"),
        ("stockkeeper", jack, "GET", "/api/v1/suppliers/"),
        ("stockkeeper", jack, "GET", "/api/v1/stock/transfers"),
        ("stockkeeper", jack, "GET", "/api/v1/store/recipes"),
        ("stockkeeper", jack, "GET", "/api/v1/staff-setup"),
        ("stockkeeper", jack, "GET", "/api/v1/notifications/"),
        ("kitchen", cook, "GET", "/api/v1/inventory/"),
        ("kitchen", cook, "GET", "/api/v1/menu/"),
        ("kitchen", cook, "GET", "/api/v1/orders/"),
        ("kitchen", cook, "GET", "/api/v1/orders/active"),
        ("kitchen", cook, "GET", "/api/v1/stock/transfers"),
        ("kitchen", cook, "GET", "/api/v1/store/recipes"),
        ("kitchen", cook, "GET", "/api/v1/notifications/"),
    ]
    seen = []
    for role, user, method, path in calls:
        response = client.request(method, path, headers=_auth(_token(user)))
        assert response.status_code == 200, f"{role} {path} -> {response.status_code} {response.text}"
        leaked = money_keys_in(response.json())
        assert leaked == [], f"{role} {path} leaked {leaked}"
        seen.append(path)
    priced = client.post(
        "/api/v1/inventory/",
        headers=_auth(_token(jack)),
        json={"item_name": "Salt", "unit": "kg", "quantity": 1, "cost_per_unit": 50},
    )
    assert priced.status_code == 422
    clean = client.post(
        "/api/v1/inventory/",
        headers=_auth(_token(jack)),
        json={"item_name": "Salt", "unit": "kg", "quantity": 1},
    )
    assert clean.status_code == 201, clean.text
    assert money_keys_in(clean.json()) == []
    assert "cost_per_unit" not in clean.json()
    # The sweep covers every parameter-free GET the role is allowed to call.
    from main import app
    for role, user in (("stockkeeper", jack), ("kitchen", cook)):
        for route in app.routes:
            methods = getattr(route, "methods", None) or set()
            path = getattr(route, "path", "")
            if "GET" not in methods or "{" in path or not path.startswith("/api/v1"):
                continue
            response = client.get(path, headers=_auth(_token(user)))
            if response.status_code != 200:
                continue
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                continue
            leaked = [key for key in money_keys_in(response.json()) if key.split(".")[-1].split("[")[0] in MONEY_KEYS]
            assert leaked == [], f"{role} {path} leaked {leaked}"


def _workbook():
    book = Workbook()
    items = book.active
    items.title = "Items"
    items.append(["item_name", "unit", "low_stock_threshold", "par_level", "cost_per_unit_kes"])
    items.append(["Rice", "kg", 2, 10, 150])
    items.append(["", "kg", 1, 1, 1])
    suppliers = book.create_sheet("Suppliers")
    suppliers.append(["name", "contact_phone", "contact_email", "notes"])
    suppliers.append(["Acme Foods", "0700000000", "acme@example.com", "Weekly"])
    recipes = book.create_sheet("Recipes")
    recipes.append(["dish_name", "category", "ingredient_name", "quantity", "unit", "yield_fraction"])
    recipes.append(["Pilau", "Mains", "Rice", 0.2, "kg", 1])
    recipes.append(["Bad dish", "Mains", "", 0.2, "kg", 1])
    opening = book.create_sheet("Opening count")
    opening.append(["item_name", "quantity", "unit"])
    opening.append(["Rice", 8, "kg"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _clean_workbook():
    book = Workbook()
    items = book.active
    items.title = "Items"
    items.append(["item_name", "unit", "low_stock_threshold", "par_level", "cost_per_unit_kes"])
    items.append(["Rice", "kg", 2, 10, 150])
    suppliers = book.create_sheet("Suppliers")
    suppliers.append(["name", "contact_phone", "contact_email", "notes"])
    suppliers.append(["Acme Foods", "0700000000", "acme@example.com", "Weekly"])
    recipes = book.create_sheet("Recipes")
    recipes.append(["dish_name", "category", "ingredient_name", "quantity", "unit", "yield_fraction"])
    recipes.append(["Pilau", "Mains", "Rice", 0.2, "kg", 1])
    opening = book.create_sheet("Opening count")
    opening.append(["item_name", "quantity", "unit"])
    opening.append(["Rice", 8, "kg"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_import_is_owner_only_idempotent_and_audited(client, db_session):
    _tenant(db_session, "Eleven", "owner-import@eleven.leviii")
    owner = db_session.query(models.User).filter_by(email="owner-import@eleven.leviii").one()
    jack = _add_staff(db_session, owner.tenant, db_session.query(models.Restaurant).one(), "jack-import@eleven.leviii", models.StaffRole.STOCKKEEPER)
    denied = client.get("/api/v1/eleven/import/template", headers=_auth(_token(jack)))
    assert denied.status_code == 403
    headers = _auth(_token(owner))
    template = client.get("/api/v1/eleven/import/template", headers=headers)
    assert template.status_code == 200
    assert template.headers["content-type"].startswith("application/vnd.openxmlformats")
    preview = client.post(
        "/api/v1/eleven/import/preview",
        headers=headers,
        files={"file": ("eleven.xlsx", _workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["error_count"] >= 1
    assert any(row["status"] == "error" for row in preview.json()["sheets"]["recipes"])
    rejected = client.post(
        "/api/v1/eleven/import/confirm",
        headers=headers,
        files={"file": ("eleven.xlsx", _workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert rejected.status_code == 400
    confirmed = client.post(
        "/api/v1/eleven/import/confirm",
        headers=headers,
        files={"file": ("eleven.xlsx", _clean_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["inserted"] == 4
    again = client.post(
        "/api/v1/eleven/import/confirm",
        headers=headers,
        files={"file": ("eleven.xlsx", _clean_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert again.status_code == 200, again.text
    assert again.json()["inserted"] == 0
    assert again.json()["skipped"] == 4
    rice = db_session.query(models.InventoryItem).filter_by(item_name="Rice").one()
    assert rice.quantity == 8
    assert rice.cost_per_unit == 150
    assert db_session.query(models.InventoryItem).filter_by(item_name="Rice").count() == 1
    jack_view = client.get("/api/v1/inventory/", headers=_auth(_token(jack)))
    assert "cost_per_unit" not in jack_view.json()[0]
    assert db_session.query(models.StaffEntryAudit).filter_by(action="import_confirmed").count() == 2
    other_tenant, other_owner, _ = _tenant(db_session, "Other Place", "other@example.com")
    foreign = client.get("/api/v1/eleven/import/template", headers=_auth(_token(other_owner)))
    assert foreign.status_code == 403
    assert other_tenant.name != "Eleven"


def test_delivery_evidence_stores_a_private_key_and_questions_are_config(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-evidence@eleven.leviii")
    receipt = models.DeliveryReceipt(
        restaurant_id=restaurant.id,
        received_by_user_id=owner.id,
        received_at=datetime.utcnow(),
        notes="",
        status="draft",
    )
    db_session.add(receipt)
    db_session.flush()
    photo = models.DeliveryEvidencePhoto(
        receipt_id=receipt.id,
        kind="invoice",
        storage_key=f"receipts/{restaurant.id}/private-evidence.jpg",
        content_type="image/jpeg",
        byte_size=12,
        sha256="abc",
        uploaded_by_user_id=owner.id,
        uploaded_at=datetime.utcnow(),
    )
    db_session.add(photo)
    db_session.add(models.DeliveryReceiptLine(
        receipt_id=receipt.id, item_name="Rice", quantity=8, unit="kg",
        keyed_by_user_id=owner.id, keyed_at=datetime.utcnow(),
    ))
    db_session.add(models.DeliveryVisionCheck(receipt_id=receipt.id, status="pending", created_at=datetime.utcnow()))
    db_session.commit()
    assert not photo.storage_key.startswith("http")
    from main import app
    paths = [getattr(route, "path", "") for route in app.routes]
    assert not any("delivery-evidence" in path or path.endswith("/receipts") for path in paths)
    setup = client.get("/api/v1/staff-setup", headers=_auth(_token(owner)))
    questions = setup.json()["steps"][2]["questions"]
    assert questions[0]["id"] == "receives_deliveries"
    assert questions[0]["answers"][0]["opens"] == "/store/stock"
    assert setup.json()["steps"][2]["runnable"] is False
    missing = client.post("/api/v1/staff-setup/questionnaire", headers=_auth(_token(owner)))
    assert missing.status_code in (404, 405)
    activity = client.get("/api/v1/staff-setup/activity", headers=_auth(_token(owner)))
    assert activity.status_code == 200
    jack = _add_staff(db_session, tenant, restaurant, "jack-activity@eleven.leviii", models.StaffRole.STOCKKEEPER)
    hidden = client.get("/api/v1/staff-setup/activity", headers=_auth(_token(jack)))
    assert hidden.status_code == 403
