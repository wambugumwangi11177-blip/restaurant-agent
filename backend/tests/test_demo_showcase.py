from datetime import date
from unittest.mock import patch
import pytest
import models
import demo_scenario as demo
from tests.test_overview_scope import scoped_owner

@pytest.fixture
def demo_headers(db_session, scoped_owner, monkeypatch):
    user, _ = scoped_owner
    import auth
    monkeypatch.setenv('DEMO_RESTAURANT_OWNER_EMAIL', user.email)
    db_session.query(models.Tenant).filter_by(id=user.tenant_id).update({'name':'Demo Restaurant'})
    db_session.query(models.Restaurant).filter_by(id=202).update({'name':'Demo Restaurant'})
    db_session.commit()
    return {'Authorization': f'Bearer {auth.create_access_token({"sub":user.email})}'}

def test_financial_reconciliation_and_calendar():
    day = date(2026, 9, 29)
    s = demo.scenario(day)
    assert len(s['history']) == 56
    assert demo.home(day=day)['revenue']['revenue'] == demo.report('daily',day)['revenue'] == 61200
    assert sum(r['sales_kes'] for r in demo.report('daily',day)['top_items']) == 61200
    assert demo.roi(day)['potential_daily'] == 2910
    assert demo.report('weekly',day)['coverage_days'] == 2
    assert demo.report('monthly',day)['coverage_days'] == 29
    assert demo.report('yearly',day)['coverage_days'] == 56
    assert s['forecast'][0]['date'] == '2026-09-30'
    assert all(r['low'] <= r['revenue'] <= r['high'] for r in s['forecast'])

def test_creative_prose_drops_truncated_tail():
    from routers.demo import complete_prose
    assert complete_prose('**Try a small experiment.** The forecast band (') == 'Try a small experiment.'
    assert complete_prose('An unfinished thought') is None
    assert complete_prose('Use the 3.2 percent estimate. Review the result.') == 'Use the 3.2 percent estimate. Review the result.'

def test_all_areas_are_populated():
    for key in demo.AREAS:
        result = demo.area(key)
        assert result['metrics'] and result['rows'] and result['action']
        assert all(len(row) == len(result['columns']) for row in result['rows'])

def test_demo_requires_authorized_identity(client, scoped_owner):
    _, headers = scoped_owner
    assert client.get('/api/v1/demo/home').status_code == 401
    assert client.get('/api/v1/demo/home',headers=headers).status_code == 403

def test_demo_reads_never_seed_business_records(client, db_session, demo_headers):
    tables = [models.Order, models.MenuItem, models.InventoryItem, models.PurchaseOrder]
    before = [db_session.query(t).count() for t in tables]
    for path in ['/home','/reports/daily', *[f'/areas/{k}' for k in demo.AREAS]]:
        r=client.get('/api/v1/demo'+path,headers=demo_headers)
        assert r.status_code == 200, r.text
    assert [db_session.query(t).count() for t in tables] == before
    assert client.get('/api/v1/demo/areas/unknown',headers=demo_headers).status_code == 404
    assert client.get('/api/v1/demo/reports/bad',headers=demo_headers).status_code == 422

def test_simulation_and_validation(client,demo_headers):
    r=client.post('/api/v1/demo/simulate',headers=demo_headers,json={'price_change_pct':0,'demand_change_pct':0})
    assert r.status_code == 200 and r.json()['delta'] == 0
    r=client.post('/api/v1/demo/simulate',headers=demo_headers,json={'price_change_pct':30,'demand_change_pct':-50})
    assert r.json()['delta'] < 0
    assert client.post('/api/v1/demo/simulate',headers=demo_headers,json={'price_change_pct':999}).status_code == 422

def test_no_provider_for_normal_chat_and_creative_cache(client,demo_headers,monkeypatch):
    from routers import demo as router
    router._cache.clear()
    with patch('ai.owner_narrative.narrate',return_value='Try a small menu experiment.') as narrate, patch('ai.creative.enabled',return_value=True):
        body={'question':'What should I do about stock?'}
        r=client.post('/api/v1/demo/chat',headers=demo_headers,json=body)
        assert r.status_code == 200 and r.json()['module']=='stock'
        assert narrate.call_count==0
        body['creative']=True
        a=client.post('/api/v1/demo/chat',headers=demo_headers,json=body)
        b=client.post('/api/v1/demo/chat',headers=demo_headers,json=body)
        assert a.json()['creative'] and b.json()['cached']
        assert narrate.call_count==1

def test_sibling_restaurant_rejected(client, db_session, scoped_owner,demo_headers):
    user,_=scoped_owner
    user.active_restaurant_id=203
    db_session.commit()
    assert client.get('/api/v1/demo/home',headers=demo_headers).status_code==403
