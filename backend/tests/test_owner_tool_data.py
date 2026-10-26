"""Regressions discovered while auditing the individual owner tools."""
from types import SimpleNamespace
from datetime import date,datetime
import models
from owner import areas
from owner.money.pnl import compute_pnl
from tests.fixtures import golden_restaurant as gr
import pytest

def test_delivery_tool_retains_every_finding(monkeypatch):
    monkeypatch.setattr(areas,'_profit',lambda ctx:{'channel_analysis':[{'channel':'glovo','orders':12,'profit':204000,'margin_pct':28.3,'commission_included':True}]})
    rows=[{'channel':'glovo','item_name':f'Dish {i}','commission_pct':25,'effective_delivery_margin':28.3,'delivery_keeps_cents':17000,'dine_in_keeps_cents':32000,'recommended_delivery_price':70000} for i in range(12)]
    monkeypatch.setattr(areas,'_pricing',lambda ctx:{'delivery_gaps':rows})
    ctx=SimpleNamespace(settings=SimpleNamespace(commission_glovo_pct=25,commission_uber_eats_pct=25,commission_bolt_food_pct=20),order_state=lambda:{'state':'live'})
    result=areas._delivery_and_dayparts(ctx)
    assert len(result['delivery_gaps'])==12
    assert result['delivery_gaps'][-1]['dish']=='Dish 11'
    assert result['delivery_gaps'][-1]['keeps']==170

@pytest.mark.parametrize('payroll,shift,expected,basis,missing',[(0,100000,105000,'shifts',False),(80000,100000,85000,'entered',False),(0,0,5000,'entered',True)])
def test_meals_do_not_replace_wages(db_session,payroll,shift,expected,basis,missing):
    g=gr.build_skeleton(db_session,now=datetime(2026,10,14,10))
    expenses=[('staff_meals',5000)]
    if payroll:expenses.append(('salaries',payroll))
    gr.seed_expenses(db_session,g,expenses,paid_on=date(2026,10,14))
    if shift:
        member=models.StaffMember(restaurant_id=g.rid,name='Test waiter',role_title='Waiter',hourly_rate=10000)
        db_session.add(member);db_session.flush()
        db_session.add(models.LaborShift(restaurant_id=g.rid,staff_member_id=member.id,shift_date=date(2026,10,14),scheduled_hours=8,actual_hours=8,labor_cost=shift))
    db_session.commit()
    result=compute_pnl(db_session,g.rid,date(2026,10,1),date(2026,10,31),today=date(2026,10,14))
    assert result['labour_cents']==expected
    assert result['labour_basis']==basis
    assert result['payroll_missing']==missing
    assert result['fixed_costs_cents']==(payroll or shift)
    assert all(section['key']!='staff' for section in result['sections'])


def test_current_labor_window_matches_pnl_and_excludes_future_and_unpaid(db_session):
    from ai.labor.intelligence import get_labor_intelligence
    g=gr.build_skeleton(db_session,now=datetime(2026,10,26,10))
    member=models.StaffMember(restaurant_id=g.rid,name='Window test',role_title='Waiter',hourly_rate=10000)
    db_session.add(member);db_session.flush()
    for day,cost in [(date(2026,9,26),900000),(date(2026,9,27),100000),(date(2026,10,26),200000),(date(2026,10,27),800000)]:
        db_session.add(models.LaborShift(restaurant_id=g.rid,staff_member_id=member.id,shift_date=day,scheduled_hours=8,actual_hours=8,labor_cost=cost))
    dish=next(iter(g.items.values()))
    gr.add_order(db_session,g,[(dish,1,500000)],datetime(2026,10,25,10))
    gr.add_order(db_session,g,[(dish,1,900000)],datetime(2026,10,25,11),paid=False)
    gr.add_order(db_session,g,[(dish,1,800000)],datetime(2026,10,27,10))
    db_session.commit()
    result=get_labor_intelligence(db_session,g.rid,now=datetime(2026,10,26,10))
    pnl=compute_pnl(db_session,g.rid,date(2026,9,27),date(2026,10,26))
    assert result['summary']['total_labor_cost_30d']==pnl['labour_cents']==300000
    assert result['summary']['total_revenue_30d']==pnl['sales_cents']==500000
    assert sum(p['labor_cost'] for p in result['staff_productivity'])==300000


def test_branch_sales_use_the_same_denominator_as_cost_percentages(monkeypatch):
    from owner.answer_compare import _branch
    restaurant=SimpleNamespace(id=1,name='Branch')
    ctx=SimpleNamespace(rid=1,now=datetime(2026,10,26,10),db=None,safe=lambda name,fn:fn())
    monkeypatch.setattr(areas,'_money_cost_dials',lambda c:{'state':'live','sales_kes':353290,'orders':110,'food_cost_pct':37.6,'wages_pct':31.2})
    monkeypatch.setattr(areas,'_overview_core',lambda c:SimpleNamespace(_summarize=lambda *args:{'revenue':374710,'orders':120}))
    result=_branch(ctx,restaurant)
    assert result['sales']==353290
    assert result['orders']==110
