"""Compatibility addresses for the former showcase, backed solely by the owner services.

The in-memory scenario remains source history/test material; it is never mounted in the live app.
Existing bookmarks and API addresses use the same active restaurant and calculations as /owner.
"""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from database import get_db
from routers import owner
from owner import areas, ask, home, reports

router = APIRouter(prefix="/demo", tags=["owner compatibility"])
AREA = {"revenue":"sales_dishes","orders":"sales_dishes","pos":"sales_dishes","menu":"sales_dishes","marketing":"sales_dishes","intelligence":"sales_dishes","forecast":"sales_dishes","stock":"store","suppliers":"store","purchasing":"store","inventory":"store","finance":"money","expenses":"money","cash-reconciliation":"cash","risk":"cash","team":"staff","kitchen":"staff","bookings":"staff","data-trust":"permits","audit":"permits","settings":"permits","notifications":"permits"}

def context(db,user):
    return owner._context(db,user)

@router.get("/home")
def legacy_home(period:Literal["today","7d","30d","1h"]="today",db:Session=Depends(get_db),user=Depends(owner._owner_only)):
    return home.compose_home(context(db,user),"today" if period=="1h" else period)

@router.get("/areas/{key}")
def legacy_area(key:str,db:Session=Depends(get_db),user=Depends(owner._owner_only)):
    key=AREA.get(key,key)
    if key not in areas.AREAS: raise HTTPException(404,"Unknown area")
    return areas.compose_area(context(db,user),key)

@router.get("/reports/{period}")
def legacy_report(period:Literal["daily","weekly","monthly","yearly"],db:Session=Depends(get_db),user=Depends(owner._owner_only)):
    return reports.compose_report(context(db,user),period)

class Question(BaseModel):
    model_config=ConfigDict(extra="forbid")
    question:str=Field(min_length=3,max_length=500)
    topic:str|None=None
    creative:bool=False
    report_period:Literal["daily","weekly","monthly","yearly"]|None=None

@router.post("/chat")
def legacy_chat(body:Question,db:Session=Depends(get_db),user=Depends(owner._owner_only)):
    result=ask.ask(context(db,user),body.question)
    return {**result,"answer_text":result["headline"],"creative":False,"cached":False,"href":"/os","module":result["topic"],"reason":result.get("reason")}

class Simulation(BaseModel):
    price_change_pct:float=Field(default=5,ge=-30,le=30,allow_inf_nan=False)
    demand_change_pct:float=Field(default=0,ge=-50,le=50,allow_inf_nan=False)

@router.post("/simulate")
def legacy_simulate(body:Simulation,db:Session=Depends(get_db),user=Depends(owner._owner_only)):
    if body.demand_change_pct != 0:
        raise HTTPException(422,"Use the shared simulator: demand comes from the displayed saved or learned assumption, not an unlabelled override.")
    # The shared simulator labels demand assumptions and never changes a price.
    direction="raise" if body.price_change_pct>=0 else "cut"
    return ask.ask(context(db,user),f"What if I {direction} my best seller by {abs(body.price_change_pct):g}%?",form="what_if")

class Ideas(BaseModel):
    creative:bool=False

@router.post("/ideas")
def legacy_ideas(body:Ideas,db:Session=Depends(get_db),user=Depends(owner._owner_only)):
    return ask.ask(context(db,user),"What should I do to make more money?",form="what_to_do")

@router.get("/reports/{period}/pdf")
def legacy_pdf(period:Literal["daily","weekly","monthly","yearly"],db:Session=Depends(get_db),user=Depends(owner._owner_only)):
    return owner.report_pdf(period,None,db,user)
