"""Add local-only demo identities; never reset existing accounts, records or PINs."""
import argparse,os,sys,json
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
locator=root/'.tmp'/'eleven-runtime-db.txt'
expected=Path(locator.read_text(encoding='utf-8').strip()) if locator.exists() else root/'backend'/'local_latest_owner.db'
allowed=(root/'backend/local_latest_owner.db',Path('D:/codex-eleven-runtime/2026-10-25/database/local_latest_owner.db'))
if expected.resolve() not in [p.resolve() for p in allowed]:raise SystemExit('Only the explicit local demo database is permitted')
os.environ['DATABASE_URL']='sqlite:///'+expected.as_posix()
os.environ['APP_ENV']='development'
sys.path.insert(0,str(root/'backend'))
from dotenv import load_dotenv
load_dotenv(root/'backend'/'.env')
import auth,models
from database import SessionLocal
password=os.environ.get('ELEVEN_DEMO_STAFF_PASSWORD')
if args.apply and not password:raise SystemExit('Set ELEVEN_DEMO_STAFF_PASSWORD for these disposable demo identities')
with SessionLocal() as db:
 tenant=db.query(models.Tenant).filter_by(name='Demo Restaurant').one()
 branches=db.query(models.Restaurant).filter_by(tenant_id=tenant.id).all()
 rows=[]
 for branch in branches:
  for index,role in enumerate([models.StaffRole.WAITER,models.StaffRole.STOCKKEEPER,models.StaffRole.CONTROLLER,models.StaffRole.KITCHEN]):
   email=f'eleven-{branch.id}-{role.value}@demo.local'
   user=db.query(models.User).filter_by(email=email).first()
   created=False
   if not user and args.apply:
    user=models.User(tenant_id=tenant.id,active_restaurant_id=branch.id,email=email,hashed_password=auth.get_password_hash(password),role=models.Role.STAFF,staff_role=role,is_active=True,hashed_pin=auth.get_pin_hash(str(4821+index*111)))
    db.add(user);db.flush();db.add(models.StaffMember(restaurant_id=branch.id,user_id=user.id,name=f'Demo {"Accountant" if role==models.StaffRole.CONTROLLER else "Chef" if role==models.StaffRole.KITCHEN else role.value.title()}',role_title=role.value));created=True
   rows.append({'branch':branch.name,'branch_id':branch.id,'role':role.value,'email':email,'created':created,'pin_if_new':str(4821+index*111) if created else 'unchanged'})
 if args.apply:db.commit()
 print(json.dumps(rows,indent=2))
