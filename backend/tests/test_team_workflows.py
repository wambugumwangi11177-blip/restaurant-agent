import auth
import models
import pytest
from tests.test_overview_scope import scoped_owner  # noqa: F401
from time_utils import eat_date, utcnow


def teammate(db, role, rid=202, tenant=101):
    u = models.User(tenant_id=tenant, active_restaurant_id=rid, email=f'{role.value}-{rid}@example.com',
                    role=models.Role.STAFF, staff_role=role, hashed_password='unused', is_active=True)
    db.add(u); db.flush()
    db.add(models.StaffMember(restaurant_id=rid, user_id=u.id, name=role.value, is_active=True))
    db.commit()
    return u, {'Authorization': 'Bearer ' + auth.create_access_token({'sub': u.email})}


def post(client, headers, **kw):
    return client.post('/api/v1/team-work', headers=headers, json={
        'request_key': 'request-001', 'restaurant_id': 202, 'kind': 'task',
        'title': 'Review a delivery', 'reason': 'Check the invoice', **kw})


def act(client, headers, item, action, revision=0):
    return client.post(f'/api/v1/team-work/{item}/transition', headers=headers,
                       json={'action': action, 'revision': revision, 'note': 'Checked the records'})


def test_task_scope_and_stale_transitions(client, db_session, scoped_owner):
    _, owner = scoped_owner
    person, staff = teammate(db_session, models.StaffRole.STOCKKEEPER)
    outsider, foreign = teammate(db_session, models.StaffRole.MANAGER, 303, 202)
    r = post(client, owner, assigned_to=person.id)
    assert r.status_code == 201, r.text
    item = r.json()['id']
    assert post(client, owner, assigned_to=person.id).json()['id'] == item
    assert post(client, owner, assigned_to=person.id, title='Different work').status_code == 409
    assert post(client, owner, request_key='other-request', assigned_to=outsider.id).status_code == 422
    assert client.get('/api/v1/team-work', headers=foreign).json()['items'] == []
    assert act(client, foreign, item, 'complete').status_code == 404
    assert act(client, staff, item, 'start').status_code == 200
    assert act(client, staff, item, 'complete').status_code == 409
    assert act(client, staff, item, 'complete', 1).json()['status'] == 'completed'
    assert act(client, staff, item, 'complete', 2).status_code == 409
    assert len(client.get('/api/v1/team-work/activity', headers=staff).json()['items']) == 3
    assert client.get('/api/v1/team-work/activity', headers=foreign).json()['items'] == []
    assert client.get('/api/v1/team-work/people', headers=staff).status_code == 403


def test_expense_proposal_requires_owner_and_unchanged_record(client, db_session, scoped_owner):
    _, owner = scoped_owner
    _, accountant = teammate(db_session, models.StaffRole.CONTROLLER)
    r = client.post('/api/v1/owner/money/expenses', headers=owner, json={
        'category': 'repairs', 'amount_kes': '120.00', 'paid_on': str(eat_date(utcnow())), 'method': 'cash'})
    assert r.status_code == 201, r.text
    expense_id = r.json()['id']
    proposal = post(client, accountant, kind='expense_void', expense_id=expense_id)
    assert proposal.status_code == 201, proposal.text
    item = proposal.json()['id']
    assert act(client, accountant, item, 'approve').status_code == 403
    expense = db_session.get(models.Expense, expense_id)
    assert expense.voided_at is None
    expense.note = 'Updated after proposal'; db_session.commit()
    assert act(client, owner, item, 'approve').status_code == 409
    proposal2 = post(client, accountant, kind='expense_void', expense_id=expense_id, request_key='request-002')
    assert act(client, owner, proposal2.json()['id'], 'approve').status_code == 200
    db_session.refresh(expense)
    assert expense.voided_at is not None
    assert act(client, owner, proposal2.json()['id'], 'approve').status_code == 409


def test_spoilage_applies_once_and_requires_current_stock(client, db_session, scoped_owner):
    _, owner = scoped_owner
    _, kitchen = teammate(db_session, models.StaffRole.KITCHEN)
    stock = db_session.query(models.InventoryItem).filter_by(restaurant_id=202).one()
    stock.quantity = 8; db_session.commit()
    r = post(client, kitchen, kind='spoilage', inventory_item_id=stock.id, quantity=2)
    assert r.status_code == 201, r.text
    stock.quantity = 7; db_session.commit()
    assert act(client, owner, r.json()['id'], 'approve').status_code == 409
    r = post(client, kitchen, kind='spoilage', inventory_item_id=stock.id, quantity=2, request_key='request-002')
    assert act(client, owner, r.json()['id'], 'approve').status_code == 200
    db_session.refresh(stock); assert stock.quantity == 5
    assert act(client, owner, r.json()['id'], 'approve').status_code == 409
    assert db_session.query(models.StockMovement).filter_by(inventory_item_id=stock.id).count() == 1
    foreign = db_session.query(models.InventoryItem).filter_by(restaurant_id=303).one()
    assert post(client, kitchen, kind='spoilage', inventory_item_id=foreign.id, quantity=1, request_key='request-003').status_code == 404


@pytest.mark.parametrize('path', ['/api/v1/team-work', '/api/v1/team-work/activity', '/api/v1/team-work/people'])
def test_foreign_selected_branch_rejected(client, db_session, scoped_owner, path):
    user, headers = scoped_owner
    user.active_restaurant_id = 303; db_session.commit()
    assert client.get(path, headers=headers).status_code == 404


def test_setup_review_is_resumable_owner_only_and_branch_scoped(client, db_session, scoped_owner):
    user, headers = scoped_owner
    r = client.get('/api/v1/owner/setup', headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()['steps']) == 6
    _, staff = teammate(db_session, models.StaffRole.MANAGER)
    assert client.get('/api/v1/owner/setup', headers=staff).status_code == 403
    body = {'restaurant_id': 202, 'note': 'Reviewed menu with the head chef'}
    assert client.post('/api/v1/owner/setup/menu/review', headers=headers, json=body).status_code == 200
    assert client.post('/api/v1/owner/setup/menu/review', headers=headers, json=body).status_code == 200
    assert db_session.query(models.TeamWorkflow).filter_by(kind='onboarding').count() == 1
    assert client.get('/api/v1/owner/setup', headers=headers).json()['steps'][0]['review']['note'] == body['note']
    assert client.get('/api/v1/team-work', headers=headers).json()['items'] == []
    user.active_restaurant_id = 203; db_session.commit()
    assert client.get('/api/v1/owner/setup', headers=headers).json()['steps'][0]['review'] is None
    assert client.post('/api/v1/owner/setup/menu/review', headers=headers, json=body).status_code == 409


def test_options_never_leak_other_branch_records(client, db_session, scoped_owner):
    _, headers = scoped_owner
    r = client.get('/api/v1/team-work/options', headers=headers)
    assert r.status_code == 200
    assert [i['name'] for i in r.json()['stock']] == ['Selected stock']
    _, waiter = teammate(db_session, models.StaffRole.WAITER)
    assert client.get('/api/v1/team-work/options', headers=waiter).json() == {'stock': [], 'expenses': []}


def test_observer_mode_refuses_new_operational_writes():
    from observer_mode import is_blocked_request
    assert is_blocked_request('POST', '/api/v1/team-work')
    assert is_blocked_request('POST', '/api/v1/team-work/1/transition')
