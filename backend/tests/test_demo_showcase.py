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

def test_creative_never_shows_model_planning_notes():
    from routers.demo import creative_final
    leaked = (
        "Constraints:\n\n- Use only supplied evidence, never calculate.\n- Two complete plain-text sentences, at most 60 words.\n\n"
        "We need to produce two sentences.\n\n"
        'Sentence 1: "The data shows three opportunities worth KES 2,910 a day."\n\n'
        'Sentence 2: "A practical test would pilot the vegetable bowl on one shift."\n\nNow count words.'
    )
    assert creative_final(leaked) == (
        "The data shows three opportunities worth KES 2,910 a day. "
        "A practical test would pilot the vegetable bowl on one shift.")
    # Planning with no drafted answer is refused rather than displayed.
    assert creative_final("Constraints:\n- Use only supplied evidence.\n- Never claim an action happened.") is None
    assert creative_final("We need to answer with two sentences about KES 720.") is None
    assert creative_final("") is None
    clean = "Vegetables expiring soon are worth KES 1,440 a day. Try a small vegetable-bowl special this week."
    assert creative_final(clean) == clean

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

def test_stock_is_built_from_the_menu_recipes():
    s = demo.scenario(date(2026, 9, 30))
    menu_dishes = {name for name, *_ in s['menu']}
    assert set(demo.RECIPES) == menu_dishes
    on_shelf = {x['name'] for x in s['stock']}
    used = {ing for recipe in demo.RECIPES.values() for ing in recipe}
    assert on_shelf == used                      # nothing on the shelf that no dish uses, nothing used that is missing
    assert all(x['used_in'] for x in s['stock'])
    assert [x['name'] for x in s['stock'] if x['low']] == ['Beef']
    beef = next(x for x in s['stock'] if x['name'] == 'Beef')
    assert beef['daily_use'] == 3.0 and beef['cover_days'] == 2.0   # 24 pilau x 0.125 kg
    assert demo.home(day=date(2026, 9, 30))['stock']['recorded_items'] == len(s['stock'])
    stock_rows = demo.area('stock', date(2026, 9, 30))['rows']
    assert len(stock_rows) == len(s['stock'])

def test_every_area_explains_itself_in_plain_words():
    for key in demo.AREAS:
        a = demo.area(key)
        assert a['headline'] and a['how_to_read'] and a['subtitle'] and a['table_title'] and a['table_note']
        assert isinstance(a['attention'], list) and isinstance(a['decisions'], list)
        for d in a['decisions']:
            assert d['idea'] and d['why'] and d['next_step']
    assert demo.area('audit')['columns'] == ['What', 'Why it matters', 'Where it stands']
    assert all(a for a in (demo.area(k)['decisions'] for k in ('revenue', 'stock', 'menu', 'team', 'suppliers')))

def test_each_forecast_day_carries_its_own_reason():
    forecast = demo.area('revenue', date(2026, 9, 30))['forecast']
    assert len(forecast) == 7
    for row in forecast:
        assert row['day'] in row['why'] and 'KES' in row['why']
    line = next(c for c in demo.area('revenue')['charts'] if c['type'] == 'line_band')
    assert len(line['actual']) == 14 and len(line['forecast']) == 7

def test_report_content_and_pdf_builder():
    from demo_report_pdf import build_pdf
    for period in ('daily', 'weekly', 'monthly', 'yearly'):
        r = demo.report(period, date(2026, 9, 30))
        assert r['headline'] and r['series'] and r['story'] and r['decisions'] and len(r['kpis']) == 4
        assert r['weekday_pattern'] and sum(c['value'] for c in r['channels']) == 70
        assert build_pdf(r).startswith(b'%PDF')
    daily = demo.report('daily', date(2026, 9, 30))
    assert 'last 7 days' in daily['story'][0]['text']

def test_report_pdf_endpoint(client, demo_headers):
    r = client.get('/api/v1/demo/reports/weekly/pdf', headers=demo_headers)
    assert r.status_code == 200 and r.content.startswith(b'%PDF')
    assert r.headers['content-type'] == 'application/pdf' and 'attachment' in r.headers['content-disposition']
    assert client.get('/api/v1/demo/reports/weekly/pdf').status_code == 401
    assert client.get('/api/v1/demo/reports/nope/pdf', headers=demo_headers).status_code == 422

def test_ideas_check_the_numbers_first_and_call_no_provider(client, demo_headers):
    with patch('ai.owner_narrative.narrate') as narrate:
        r = client.post('/api/v1/demo/ideas', headers=demo_headers, json={})
        assert r.status_code == 200
        body = r.json()
        assert body['checked'] == len(demo.AREAS) and body['creative'] == []
        assert body['from_numbers'] and all(i['idea'] and i['why'] and i['next_step'] for i in body['from_numbers'])
        assert narrate.call_count == 0
    assert client.post('/api/v1/demo/ideas', json={}).status_code == 401

def test_creative_ideas_use_only_the_final_block_and_are_cached(client, demo_headers):
    from routers import demo as router
    router._cache.clear()
    raw = ("We need four ideas. Constraints: one sentence each.\nIdea 1: draft only\n"
           "FINAL:\n1. Offer a lunch combo of vegetable bowl and fresh juice.\n"
           "2. Run a chai and mandazi special on your quietest afternoon.\n"
           "3. Ask regular guests to order takeaway by M-Pesa message.\n")
    with patch('ai.owner_narrative.narrate', return_value=raw) as narrate, patch('ai.creative.enabled', return_value=True):
        a = client.post('/api/v1/demo/ideas', headers=demo_headers, json={'creative': True}).json()
        b = client.post('/api/v1/demo/ideas', headers=demo_headers, json={'creative': True}).json()
    assert a['creative'] == [
        'Offer a lunch combo of vegetable bowl and fresh juice.',
        'Run a chai and mandazi special on your quietest afternoon.',
        'Ask regular guests to order takeaway by M-Pesa message.']
    assert not a['cached'] and b['cached'] and narrate.call_count == 1

def test_creative_final_contract_and_ideas_parser():
    from routers.demo import creative_final, creative_ideas
    leaked = "Constraints:\n- two sentences\nWe need to be brief.\nFINAL: Use the vegetables first. Sell a vegetable bowl special."
    assert creative_final(leaked) == "Use the vegetables first. Sell a vegetable bowl special."
    assert creative_final("Constraints:\n- two sentences\nWe need to be brief.") is None     # truncated before FINAL
    assert creative_final("FINAL: We need to compute the word count.") is None
    assert creative_ideas("no final block here\n1. Something useful to try this week.") == []
    assert creative_ideas("FINAL:\n- Try a lunch combo this week.\n- ok\n- Sell chai to takeaway guests on quiet days.") == [
        "Try a lunch combo this week.", "Sell chai to takeaway guests on quiet days."]

def test_prompted_questions_route_to_the_right_area_without_a_provider(client, demo_headers):
    from routers.demo import answer_topic
    assert answer_topic('Where can I save money?', None) == 'intelligence'
    assert answer_topic('Will I run out of beef?', None) == 'stock'
    assert answer_topic('Why is Monday so quiet?', 'revenue') == 'revenue'
    with patch('ai.owner_narrative.narrate') as narrate:
        r = client.post('/api/v1/demo/chat', headers=demo_headers, json={'question': 'What should I do about my menu prices?'})
        j = r.json()
        assert j['module'] == 'menu' and 'An idea:' in j['answer_text'] and j['follow_ups']
        r = client.post('/api/v1/demo/chat', headers=demo_headers, json={'question': 'Why does revenue look like this?', 'topic': 'revenue'})
        assert 'next 7 days' in r.json()['answer_text']
        assert narrate.call_count == 0

def test_sibling_restaurant_rejected(client, db_session, scoped_owner,demo_headers):
    user,_=scoped_owner
    user.active_restaurant_id=203
    db_session.commit()
    assert client.get('/api/v1/demo/home',headers=demo_headers).status_code==403
