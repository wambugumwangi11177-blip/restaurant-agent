"""Platform admin staff list and handover reset (Company OS API)."""
import auth
import models
from tests.test_data_wall_eleven import _seed_pair, _token


def _service_headers(monkeypatch, actor_email: str, token: str = "test-platform-token") -> dict:
    monkeypatch.setenv("COMPANY_OS_SERVICE_TOKEN", token)
    monkeypatch.setenv("COMPANY_OS_ACTOR_EMAIL", actor_email)
    return {"X-Company-OS-Token": token}


def test_owner_cannot_list_or_reset_platform_staff(client, db_session):
    owner, jack, _, eleven_r, _ = _seed_pair(db_session)
    listed = client.get(f"/api/v1/admin/platform/restaurants/{eleven_r.id}/staff", headers=_token(owner))
    assert listed.status_code == 403
    reset = client.post(
        f"/api/v1/admin/platform/restaurants/{eleven_r.id}/staff/{jack.id}/reset-sign-in",
        headers=_token(owner),
    )
    assert reset.status_code == 403


def test_service_token_lists_staff_and_resets_sign_in(client, db_session, monkeypatch):
    owner, jack, test_o, eleven_r, test_r = _seed_pair(db_session)
    headers = _service_headers(monkeypatch, owner.email)

    eleven_staff = client.get(f"/api/v1/admin/platform/restaurants/{eleven_r.id}/staff", headers=headers)
    assert eleven_staff.status_code == 200, eleven_staff.text
    emails = {row["email"] for row in eleven_staff.json()}
    assert owner.email in emails
    assert jack.email in emails
    assert test_o.email not in emails

    test_staff = client.get(f"/api/v1/admin/platform/restaurants/{test_r.id}/staff", headers=headers)
    assert test_staff.status_code == 200
    test_emails = {row["email"] for row in test_staff.json()}
    assert test_o.email in test_emails
    assert jack.email not in test_emails

    reset = client.post(
        f"/api/v1/admin/platform/restaurants/{eleven_r.id}/staff/{jack.id}/reset-sign-in",
        headers=headers,
    )
    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert body["email"] == jack.email
    assert body["handover_code"].isdigit() and len(body["handover_code"]) == 6
    assert body["expires_at"]
    db_session.refresh(jack)
    assert jack.hashed_password is None
    assert jack.password_reset_required is True

    # A Test Restaurant staff id is not reset through Eleven's restaurant.
    cross = client.post(
        f"/api/v1/admin/platform/restaurants/{eleven_r.id}/staff/{test_o.id}/reset-sign-in",
        headers=headers,
    )
    assert cross.status_code == 404


def test_service_token_creates_staff_on_one_client_only(client, db_session, monkeypatch):
    owner, _, _, eleven_r, test_r = _seed_pair(db_session)
    headers = _service_headers(monkeypatch, owner.email)
    created = client.post(
        f"/api/v1/admin/platform/restaurants/{test_r.id}/staff",
        headers=headers,
        json={"email": "new-keeper@test.leviii", "staff_role": "stockkeeper", "display_name": "Keeper"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["email"] == "new-keeper@test.leviii"

    eleven_staff = client.get(f"/api/v1/admin/platform/restaurants/{eleven_r.id}/staff", headers=headers)
    assert "new-keeper@test.leviii" not in {row["email"] for row in eleven_staff.json()}
    test_staff = client.get(f"/api/v1/admin/platform/restaurants/{test_r.id}/staff", headers=headers)
    assert "new-keeper@test.leviii" in {row["email"] for row in test_staff.json()}
