import subprocess
import time
import requests
import sys
import os
import random
import string

def verify_auth():
    print("Starting backend server for auth verification...", flush=True)
    # diverse paths handling
    if os.name == 'nt':
        uvicorn_cmd = os.path.join("backend", "venv", "Scripts", "uvicorn")
    else:
        uvicorn_cmd = os.path.join("backend", "venv", "bin", "uvicorn")
        
    process = subprocess.Popen(
        [uvicorn_cmd, "main:app", "--port", "8002"],
        cwd="backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        print("Waiting for server to start...", flush=True)
        time.sleep(5) 
        
        base_url = "http://localhost:8002"
        
        # Generate random user to avoid conflicts
        rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        email = f"user_{rand_str}@example.com"
        password = "secretpassword"
        tenant = f"Tenant_{rand_str}"
        
        print(f"\n1. Registering new user: {email}...", flush=True)
        resp = requests.post(f"{base_url}/auth/register", json={
            "email": email,
            "password": password,
            "tenant_name": tenant
        })
        print(f"Status: {resp.status_code}", flush=True)
        if resp.status_code == 200:
            print("Response:", resp.json(), flush=True)
            token = resp.json().get("access_token")
        else:
            print("FAILED to register:", resp.text, flush=True)
            return

        print(f"\n2. Logging in as {email}...", flush=True)
        resp = requests.post(f"{base_url}/auth/login", data={
            "username": email,
            "password": password
        })
        print(f"Status: {resp.status_code}", flush=True)
        if resp.status_code == 200:
            print("Login SUCCESS", flush=True)
            token_login = resp.json().get("access_token")
        else:
            print("FAILED to login:", resp.text, flush=True)
            return

        print("\n3. Verifying /auth/me with token...", flush=True)
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{base_url}/auth/me", headers=headers)
        print(f"Status: {resp.status_code}", flush=True)
        print("Response:", resp.json(), flush=True)
        
        if resp.status_code == 200 and resp.json().get("email") == email:
            print("SUCCESS: /auth/me returned correct user", flush=True)
        else:
            print("FAILED: /auth/me check failed", flush=True)

    finally:
        print("\nStopping server...", flush=True)
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            print("Force killing server...", flush=True)
            process.kill()
            
        stdout, stderr = process.communicate()
        # print output for debugging if needed
        # print(stdout.decode())

if __name__ == "__main__":
    verify_auth()
