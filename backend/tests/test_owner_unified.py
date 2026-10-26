"""One record set across current and historical addresses; real main.app integration."""
import pytest
import models
from tests.test_overview_scope import scoped_owner

@pytest.mark.parametrize("path,alias",[("/owner/home","/demo/home"),("/owner/area/money","/demo/areas/finance"),("/owner/report/monthly","/demo/reports/monthly")])
def test_demo_addresses_read_the_same_operational_values(client,scoped_owner,path,alias):
    _,headers=scoped_owner
    current=client.get("/api/v1"+path,headers=headers)
    former=client.get("/api/v1"+alias,headers=headers)
    assert current.status_code==former.status_code==200
    def stable(value):
        if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in {"as_of","generated_at"}}
        if isinstance(value,list):return [stable(v) for v in value]
        return value
    assert stable(former.json())==stable(current.json())

def test_question_compatibility_does_not_use_in_memory_scenario(client,scoped_owner,monkeypatch):
    import demo_scenario
    monkeypatch.setattr(demo_scenario,"home",lambda *a,**kw: (_ for _ in ()).throw(AssertionError("scenario accessed")))
    _,headers=scoped_owner
    q={"question":"How is my cash count looking?"}
    canonical=client.post('/api/v1/owner/ask',json=q,headers=headers).json()
    alias=client.post('/api/v1/demo/chat',json=q,headers=headers).json()
    assert alias['headline']==canonical['headline']
    assert alias['rows']==canonical['rows']
    assert alias['creative'] is False

def test_daily_sales_and_month_pnl_agree_across_surfaces(client,db_session,scoped_owner):
    from time_utils import utcnow
    user,headers=scoped_owner
    db_session.add(models.Order(restaurant_id=202,table_number=1,status=models.OrderStatus.SERVED,is_paid=True,total=123400,created_at=utcnow()))
    db_session.add(models.Order(restaurant_id=203,table_number=1,status=models.OrderStatus.SERVED,is_paid=True,total=999900,created_at=utcnow()))
    db_session.commit()
    h=client.get('/api/v1/owner/home',headers=headers).json()
    daily=client.get('/api/v1/owner/report/daily',headers=headers).json()
    daily_sales=next(s for s in daily['sections'] if s['key']=='sales')
    assert h['pulse']['sales_today']==daily_sales['sales']==1234
    area=client.get('/api/v1/owner/area/money',headers=headers).json()
    monthly=client.get('/api/v1/owner/report/monthly',headers=headers).json()
    pnl=next(s for s in monthly['sections'] if s['key']=='pnl')
    ledger=client.get('/api/v1/owner/money/pnl?period=month',headers=headers).json()
    for key in ['sales','food_cost','gross_profit','wages','operating_expenses','operating_profit']:
        if key in pnl:
            assert pnl[key]==h['areas']['money']['blocks']['pnl'][key]==area['blocks']['pnl'][key]==ledger[key]
    assert pnl['lines']==ledger['lines']==area['blocks']['pnl']['lines']

def test_old_api_has_owner_access_checks(client,scoped_owner,db_session):
    user,headers=scoped_owner
    user.role=models.Role.STAFF
    user.staff_role=models.StaffRole.WAITER
    db_session.commit()
    assert client.get('/api/v1/demo/home',headers=headers).status_code==403


def test_report_pdf_uses_canonical_payload(client,scoped_owner):
    _,headers=scoped_owner
    response=client.get('/api/v1/owner/report/weekly/pdf',headers=headers)
    assert response.status_code==200
    assert response.content.startswith(b'%PDF')
    old=client.get('/api/v1/demo/reports/weekly/pdf',headers=headers)
    assert old.status_code==200 and old.content.startswith(b'%PDF')


def test_calendar_week_total_matches_all_seven_bars_and_report_at_midday(client,db_session,scoped_owner,monkeypatch):
    from datetime import datetime, timedelta
    from routers import overview,reports
    now=datetime(2026,10,25,9,0)
    monkeypatch.setattr(overview,"_eat_now",lambda:now+timedelta(hours=3))
    monkeypatch.setattr(reports,"utcnow",lambda:now)
    _,headers=scoped_owner
    # First calendar day at 08:00 Nairobi is included; an eighth day and a future sale are excluded.
    for when,cents in [(datetime(2026,10,19,5),120000),(datetime(2026,10,18,20),990000),(datetime(2026,10,25,10),880000)]:
        db_session.add(models.Order(restaurant_id=202,table_number=1,status=models.OrderStatus.SERVED,is_paid=True,total=cents,created_at=when))
    db_session.commit()
    start,end=overview._eat_range('7d')
    total=overview._summarize(db_session,202,start,end)['revenue']
    bars=overview._performance(db_session,202)['revenue_trend']
    assert total==sum(d['revenue'] for d in bars)==1200
    assert reports._range('weekly')==(start,end)


def test_a_team_expense_flows_to_home_report_and_accountant_without_refreshing_data(client,scoped_owner):
    _,headers=scoped_owner
    client.get('/api/v1/owner/money/categories',headers=headers)
    before=client.get('/api/v1/owner/money/pnl?period=month',headers=headers).json()
    old={r['key']:r['kes'] for r in before['lines']}
    saved=client.post('/api/v1/owner/money/expenses',headers=headers,json={'category':'kplc','amount_kes':'123.45','method':'cash','entry_key':'unified-expense-123'})
    assert saved.status_code==201
    h=client.get('/api/v1/owner/home',headers=headers).json()
    report=client.get('/api/v1/owner/report/monthly',headers=headers).json()
    accountant=client.get('/api/v1/owner/money/pnl?period=month',headers=headers).json()
    pnl=next(s for s in report['sections'] if s['key']=='pnl')
    assert h['areas']['money']['blocks']['pnl']['lines']==pnl['lines']==accountant['lines']
    new={r['key']:r['kes'] for r in pnl['lines']}
    assert round(new['other_costs']-old['other_costs'],2)==-123.45
    assert round(new['kept']-old['kept'],2)==-123.45
