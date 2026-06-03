import os
import subprocess
import sys

def run_command(command, cwd=None):
    print(f"Running: {command}")
    try:
        subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            check=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        sys.exit(1)

def setup_auth_backend():
    backend_dir = "backend"
    if not os.path.exists(backend_dir):
        print("Backend directory not found. Please run setup.py first.")
        return

    # Install dependencies
    print("Installing Auth dependencies...")
    venv_path = os.path.join(backend_dir, "venv")
    if os.name == 'nt':
        pip_cmd = os.path.join(venv_path, "Scripts", "pip")
    else:
        pip_cmd = os.path.join(venv_path, "bin", "pip")

    run_command(f"\"{pip_cmd}\" install \"python-jose[cryptography]\" \"passlib[bcrypt]\" \"python-multipart\"")

    # Create auth.py
    auth_py_path = os.path.join(backend_dir, "auth.py")
    if not os.path.exists(auth_py_path):
        print("Creating backend/auth.py...")
        with open(auth_py_path, "w") as f:
            f.write("""from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key_here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        # In a real app, verify user exists in DB here
        return {"email": email} 
    except JWTError:
        raise credentials_exception
""")
        print("Created auth.py")

if __name__ == "__main__":
    setup_auth_backend()
