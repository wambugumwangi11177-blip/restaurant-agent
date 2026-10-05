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

@pytest.fixture(autouse=True)
def _reset_ai_guard():
    from routers import demo as router
    router._ai_paused_until[0] = 0.0
    yield
    router._ai_paused_until[0] = 0.0

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

def test_stock_learns_from_expected_sales_and_feeds_the_other_modules():
    day = date(2026, 9, 30)
    s = demo.scenario(day)
    beef = next(x for x in s['stock'] if x['name'] == 'Beef')
    # Cover at today's rate is 2.0 days, but Friday and Saturday sell more, so beef runs out sooner.
    assert beef['cover_days'] == 2.0 and beef['runway_days'] == 1.9
    assert beef['runs_out_day'] == 'Friday' and beef['order_by'] == 'Today' and beef['order_qty'] == 16
    f = s['forecast']
    assert f[2]['plates'] > f[0]['plates'] and f[2]['people'] > f[0]['people'] and f[2]['covers'] > f[0]['covers']
    assert all(x['order_qty'] > 0 for x in s['stock'] if x['runs_out_day'])
    assert all(x['order_qty'] == 0 for x in s['stock'] if not x['runs_out_day'])
    assert 'beef runs out on Friday' in demo.area('stock', day)['headline']
    assert demo.home(day=day)['stock']['low_stock'][0]['runs_out_day'] == 'Friday'
    for key in ('kitchen', 'team', 'bookings', 'purchasing'):
        tables = demo.area(key, day)['extra_tables']
        assert tables, key
        for t in tables:
            assert t['rows'] and all(len(r) == len(t['columns']) for r in t['rows'])
    orders = demo.area('purchasing', day)['extra_tables'][0]['rows']
    assert orders[0][0] == 'Meat & fish partner' and 'Beef 16 kg' in orders[0][1] and orders[0][2] == 'Today'
    team = demo.area('team', day)['extra_tables'][0]['rows']
    assert next(r for r in team if r[0] == 'Saturday')[2] > next(r for r in team if r[0] == 'Thursday')[2]

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
    from routers.demo import IDEA_AREAS
    with patch('ai.owner_narrative.narrate') as narrate:
        r = client.post('/api/v1/demo/ideas', headers=demo_headers, json={})
        assert r.status_code == 200
        body = r.json()
        # "Checked" is the number of areas whose ideas were actually read, not every area in the demo.
        assert body['checked'] == len(IDEA_AREAS) and body['creative'] == []
        # One idea per area before any area's second, so the short list is not all stock and suppliers.
        assert len({i['area'] for i in body['from_numbers']}) == len(body['from_numbers'])
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

def test_web_research_is_off_unless_enabled_on_openrouter(client, demo_headers, monkeypatch):
    from routers import demo as router
    from ai import llm_client
    router._cache.clear()
    monkeypatch.delenv('DEMO_IDEAS_WEB', raising=False)
    assert router.web_research_on() is False
    monkeypatch.setenv('DEMO_IDEAS_WEB', 'true')
    monkeypatch.setattr(llm_client, '_PROVIDER', 'groq')
    assert router.web_research_on() is False
    monkeypatch.setattr(llm_client, '_PROVIDER', 'openrouter')
    assert router.web_research_on() is True
    raw = "FINAL:\n1. Offer a lunch combo of vegetable bowl and fresh juice.\n"
    with patch('ai.owner_narrative.narrate', return_value=raw) as narrate, patch('ai.creative.enabled', return_value=True):
        client.post('/api/v1/demo/ideas', headers=demo_headers, json={'creative': True})
    assert narrate.call_args.kwargs['extra_body'] == {**router.REASONING_OFF, **router.WEB_PLUGIN}
    router._cache.clear()
    monkeypatch.delenv('DEMO_IDEAS_WEB')
    with patch('ai.owner_narrative.narrate', return_value=raw) as narrate, patch('ai.creative.enabled', return_value=True):
        client.post('/api/v1/demo/ideas', headers=demo_headers, json={'creative': True})
    assert narrate.call_args.kwargs['extra_body'] == router.REASONING_OFF      # thinking off, no web search
    router._cache.clear()
    monkeypatch.setattr(llm_client, '_PROVIDER', 'groq')                        # other providers get neither field
    with patch('ai.owner_narrative.narrate', return_value=raw) as narrate, patch('ai.creative.enabled', return_value=True):
        client.post('/api/v1/demo/ideas', headers=demo_headers, json={'creative': True})
    assert 'extra_body' not in narrate.call_args.kwargs

def test_a_model_that_cannot_switch_thinking_off_is_asked_again_without_it(client, demo_headers, monkeypatch):
    from routers import demo as router
    from ai import llm_client
    router._cache.clear()
    monkeypatch.setattr(llm_client, '_PROVIDER', 'openrouter')
    monkeypatch.delenv('DEMO_IDEAS_WEB', raising=False)
    good = "FINAL:\n1. Offer a lunch combo of vegetable bowl and fresh juice.\n2. Run a chai special on quiet afternoons.\n"
    with patch('ai.owner_narrative.narrate', side_effect=[RuntimeError('400 reasoning cannot be disabled'), good]) as narrate, patch('ai.creative.enabled', return_value=True):
        body = client.post('/api/v1/demo/ideas', headers=demo_headers, json={'creative': True}).json()
    assert narrate.call_count == 2
    assert narrate.call_args_list[0].kwargs['extra_body'] == router.REASONING_OFF
    assert 'extra_body' not in narrate.call_args_list[1].kwargs
    assert len(body['creative']) == 2

def test_a_failing_provider_pauses_ai_for_everyone_and_the_site_keeps_working(client, demo_headers):
    from routers import demo as router
    router._cache.clear()
    with patch('ai.owner_narrative.narrate', side_effect=RuntimeError('provider down')) as narrate, patch('ai.creative.enabled', return_value=True):
        first = client.post('/api/v1/demo/chat', headers=demo_headers, json={'question': 'What should I do about stock?', 'creative': True})
        second = client.post('/api/v1/demo/chat', headers=demo_headers, json={'question': 'Is my staff overtime too high?', 'creative': True})
        home = client.get('/api/v1/demo/home', headers=demo_headers)
    for r in (first, second):
        assert r.status_code == 200 and not r.json()['creative'] and r.json()['answer_text']   # the calculated answer is still there
    assert narrate.call_count == 1                 # the second question did not call the provider again
    assert home.status_code == 200

def test_a_second_ai_request_skips_instead_of_queueing_behind_the_first(client, demo_headers):
    from routers import demo as router
    router._cache.clear()
    assert router._ai_slot.acquire(timeout=1)
    try:
        with patch('ai.owner_narrative.narrate') as narrate, patch('ai.creative.enabled', return_value=True):
            r = client.post('/api/v1/demo/chat', headers=demo_headers, json={'question': 'What should I do about stock?', 'creative': True})
        assert r.status_code == 200 and not r.json()['creative'] and narrate.call_count == 0
    finally:
        router._ai_slot.release()

def test_creative_final_contract_and_ideas_parser():
    from routers.demo import creative_final, creative_ideas
    leaked = "Constraints:\n- two sentences\nWe need to be brief.\nFINAL: Use the vegetables first. Sell a vegetable bowl special."
    assert creative_final(leaked) == "Use the vegetables first. Sell a vegetable bowl special."
    assert creative_final("Constraints:\n- two sentences\nWe need to be brief.") is None     # truncated before FINAL
    assert creative_final("FINAL: We need to compute the word count.") is None
    assert creative_ideas("no final block here\n1. Something useful to try this week.") == []
    assert creative_ideas("FINAL:\nEach on its own line.") == []                  # an echoed instruction is not an idea
    assert creative_ideas("FINAL:\n1. Offer a lunch combo this week.") == []       # a single stray line is not a list
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

def test_home_service_figures_match_the_area_pages():
    day = date(2026, 9, 30)
    h = demo.home(day=day)
    assert h['orders']['delayed'] == h['kitchen']['delay_risk'] == demo.DELAYED_ORDERS
    assert h['orders']['active_now'] == demo.OPEN_ORDERS
    orders = {m['label']: m['value'] for m in demo.area('orders', day)['metrics']}
    assert (orders['Open'], orders['Delayed']) == (h['orders']['active_now'], h['orders']['delayed'])
    kitchen = demo.area('kitchen', day)
    assert f"{h['kitchen']['avg_prep_min']} min" in {m['label']: m['value'] for m in kitchen['metrics']}.values()
    assert h['kitchen']['bottleneck'] == demo.BOTTLENECK
    bookings = {m['label']: m['value'] for m in demo.area('bookings', day)['metrics']}
    assert bookings['Waitlist'] == h['bookings']['waitlist'] and bookings['Expected covers'] == h['bookings']['covers_today']
    team = {m['label']: m['value'] for m in demo.area('team', day)['metrics']}
    assert (team['Scheduled'], team['On shift']) == (h['staff']['scheduled'], h['staff']['on_shift'])
    labor = next(o for o in demo.scenario(day)['opportunities'] if o['id'] == 'labor')
    assert h['staff']['overtime_risk'] == labor['quantity'] == demo.OVERTIME_HOURS

def test_home_attention_is_urgent_first_unique_and_traceable():
    day = date(2026, 9, 30)
    h = demo.home(day=day)
    ids = [c['id'] for c in h['attention'] + h['watching']]
    assert len(ids) == len(set(ids))
    levels = [c['level'] for c in h['attention']]
    assert levels == sorted(levels, key=lambda l: l != 'urgent')       # urgent first
    assert {'late-orders', 'grill', 'beef-low', 'waste', 'margin', 'labor'} <= set(ids)
    assert not {'veg-expiry', 'pilau-price', 'dinner', 'unmatched-pay', 'beef-notify'} & set(ids)
    from_areas = {a['id'] for k in demo.AREAS if k != 'notifications' for a in demo.area(k, day)['attention']}
    from_ideas = {o['id'] for o in demo.scenario(day)['opportunities']}
    assert set(ids) <= from_areas | from_ideas                           # nothing is made up for Home
    for c in h['attention'] + h['watching']:
        assert c['title'] and c['why'] and c['what_to_do'] and c['link'] in demo.AREAS
    for c in h['attention']:
        if c['level'] == 'opportunity':
            assert c['impact'].startswith('KES ') and 'potential' in c['impact']

def test_notifications_page_is_the_home_list():
    day = date(2026, 9, 30)
    h = demo.home(day=day)
    n = demo.area('notifications', day)
    total = len(h['attention']) + len(h['watching'])
    assert len(n['rows']) == total
    assert {m['label']: m['value'] for m in n['metrics']}['Need attention'] == total
    urgent = sum(1 for c in h['attention'] + h['watching'] if c['level'] == 'urgent')
    assert {m['label']: m['value'] for m in n['metrics']}['Urgent'] == urgent

def test_home_stock_and_extra_blocks_come_from_the_scenario():
    day = date(2026, 9, 30)
    s = demo.scenario(day)
    h = demo.home(day=day)
    soon = [x for x in s['stock'] if x['runway_days'] <= demo.SOON_DAYS]
    stock_metrics = {m['label']: m['value'] for m in demo.area('stock', day)['metrics']}
    assert h['stock']['soon_count'] == len(soon) == stock_metrics[f'Run out within {demo.SOON_DAYS:g} days']
    first_low = next(x for x in s['stock'] if x['low'])
    assert h['stock']['first_low_order'] == {k: first_low[k] for k in ('name', 'order_by', 'order_qty', 'unit')}
    assert first_low['name'] == 'Beef'                                   # the demo's story: beef is the urgent one
    assert h['money_today'] == demo.report('daily', day)['money_today']
    assert [r['revenue'] for r in h['week_ahead']] == [r['revenue'] for r in s['forecast']]
    assert [(r['plates'], r['people'], r['covers']) for r in h['week_ahead']] == [(r['plates'], r['people'], r['covers']) for r in s['forecast']]
    assert h['roi']['potential_daily'] == sum(o['value'] for o in s['opportunities']) and h['roi']['realised'] == 0
    assert all(p['link'] in demo.AREAS for p in h['pulse'])

def test_home_periods_are_labelled_and_summed_correctly():
    day = date(2026, 9, 30)
    s = demo.scenario(day)
    for period, n in (('today', 1), ('7d', 7), ('30d', 30)):
        h = demo.home(period, day)
        assert h['revenue']['revenue'] == sum(r['revenue'] for r in s['history'][-n:])
        assert h['period_label'] and h['period_note']
    assert 'not a live hour' in demo.home('1h', day)['period_note']

@pytest.fixture
def fresh_caches():
    """The scenario and its derived lists are cached per day; clear them around a test that changes a figure."""
    from routers import demo as router
    def clear():
        demo.scenario.cache_clear()
        demo.attention_items.cache_clear()
        router._ideas_by_area.cache_clear()
    clear()
    yield
    clear()

def test_changing_a_scenario_figure_changes_every_place_that_shows_it(monkeypatch, fresh_caches):
    day = date(2026, 9, 30)
    monkeypatch.setattr(demo, 'ORDERS_TODAY', 80)
    monkeypatch.setattr(demo, 'OVERTIME_HOURS', 5)
    h = demo.home(day=day)
    assert h['orders']['orders'] == 80 and sum(h['orders']['split'].values()) == 80
    pos = demo.area('pos', day)
    assert pos['headline'].startswith('80 orders')
    assert {m['label']: m['value'] for m in pos['metrics']}['Completed orders'] == 80
    assert sum(r[1] for r in pos['rows']) == 80
    assert 'from 80 orders' in demo.area('revenue', day)['headline']
    assert sum(c['value'] for c in demo.report('daily', day)['channels']) == 80
    assert h['staff']['overtime_risk'] == 5
    team = demo.area('team', day)
    assert 'Move 5 hours' in team['attention'][0]['what_to_do'] and 'Shift 5 hours' in team['decisions'][0]['next_step']

def test_bookings_purchase_orders_and_channels_add_up():
    day = date(2026, 9, 30)
    assert sum(covers for _, covers, _ in demo.BOOKING_SLOTS) == demo.COVERS_TODAY
    assert sum(r[1] for r in demo.area('bookings', day)['rows']) == demo.COVERS_TODAY
    total = sum(p[2] for p in demo.PURCHASE_ORDERS)
    purchasing = demo.area('purchasing', day)
    assert {m['label']: m['value'] for m in purchasing['metrics']}['Commitments'] == demo.money(total)
    assert demo.money(total) in purchasing['headline']
    assert [r[0] for r in purchasing['rows']] == [p[0] for p in demo.PURCHASE_ORDERS]
    pos = demo.area('pos', day)
    assert sum(r[1] for r in pos['rows']) == demo.ORDERS_TODAY == demo.home(day=day)['orders']['orders']
    marketing = {m['label']: m['value'] for m in demo.area('marketing', day)['metrics']}
    assert marketing['Returning guests'] + marketing['New guests'] == demo.ORDERS_TODAY

def test_repeated_alerts_point_at_a_card_home_shows():
    day = date(2026, 9, 30)
    h = demo.home(day=day)
    shown = {c['id'] for c in h['attention'] + h['watching']}
    tagged = [a for k in demo.AREAS if k != 'notifications' for a in demo.area(k, day)['attention'] if a.get('repeat_of')]
    assert tagged
    assert all(a['repeat_of'] in shown for a in tagged)       # the card that says it instead is on Home
    assert not {a['id'] for a in tagged} & shown               # and the repeat itself is not

def test_sibling_restaurant_rejected(client, db_session, scoped_owner,demo_headers):
    user,_=scoped_owner
    user.active_restaurant_id=203
    db_session.commit()
    assert client.get('/api/v1/demo/home',headers=demo_headers).status_code==403
