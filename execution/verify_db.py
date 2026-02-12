import sys
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path
sys.path.append(os.getcwd())

# Import models and db session
from backend.database import SessionLocal, engine
from backend import models

def verify_db():
    print("Verifying database...")
    db = SessionLocal()
    try:
        # Check if we can insert a tenant
        # Use a unique name to avoid errors on re-run if we verify multiple times
        # OR just check if any exists and create if not.
        
        print("Checking for existing tenants...")
        stmt = select(models.Tenant).limit(1)
        existing_tenant = db.execute(stmt).scalar_one_or_none()
        
        if not existing_tenant:
            print("No tenants found. Creating test tenant...")
            new_tenant = models.Tenant(name="Test Restaurant", plan="free")
            db.add(new_tenant)
            db.commit()
            db.refresh(new_tenant)
            print(f"Created Tenant: {new_tenant.name} (ID: {new_tenant.id})")
            tenant_id = new_tenant.id
        else:
            print(f"Found existing tenant: {existing_tenant.name} (ID: {existing_tenant.id})")
            tenant_id = existing_tenant.id
            
        # Check for user
        stmt = select(models.User).where(models.User.email == "admin@test.com")
        existing_user = db.execute(stmt).scalar_one_or_none()
        
        if not existing_user:
            print("Creating test admin user...")
            # Note: In real app we hash password. Here just testing DB persistence.
            new_user = models.User(
                email="admin@test.com",
                hashed_password="hashed_secret",
                role=models.Role.ADMIN,
                tenant_id=tenant_id
            )
            db.add(new_user)
            db.commit()
            print("Created User: admin@test.com")
        else:
            print("Found existing user: admin@test.com")
            
        print("Database verification SUCCESS!")
        
    except Exception as e:
        print(f"Database verification FAILED: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    verify_db()
