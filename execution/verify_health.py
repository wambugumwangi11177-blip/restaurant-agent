import subprocess
import time
import requests
import sys
import os

def verify_health():
    print("Starting backend server for verification...")
    # diverse paths handling
    if os.name == 'nt':
        uvicorn_cmd = os.path.join("backend", "venv", "Scripts", "uvicorn")
    else:
        uvicorn_cmd = os.path.join("backend", "venv", "bin", "uvicorn")
        
    process = subprocess.Popen(
        [uvicorn_cmd, "main:app", "--port", "8001"],
        cwd="backend",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        print("Waiting for server to start...")
        time.sleep(5) # Wait for startup
        
        base_url = "http://localhost:8001"
        
        # 1. Health Check
        print("\nChecking /health...")
        try:
            resp = requests.get(f"{base_url}/health")
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.json()}")
            if resp.status_code != 200:
                print("FAILED: /health did not return 200")
        except Exception as e:
            print(f"FAILED: Could not connect to /health: {e}")

        # 2. DB Health Check
        print("\nChecking /health/db...")
        try:
            resp = requests.get(f"{base_url}/health/db")
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.json()}")
            # It might fail if DB is not configured, but we check if endpoint exists
        except Exception as e:
            print(f"FAILED: Could not connect to /health/db: {e}")

        # 3. Timing Middleware
        print("\nChecking Timing Middleware (on /)...")
        try:
            resp = requests.get(f"{base_url}/")
            print(f"Status: {resp.status_code}")
            process_time = resp.headers.get("X-Process-Time")
            print(f"X-Process-Time: {process_time}")
            if process_time:
                print("SUCCESS: X-Process-Time header present")
            else:
                print("FAILED: X-Process-Time header missing")
        except Exception as e:
            print(f"FAILED: Could not connect to /: {e}")

        # 4. Webhook
        print("\nChecking Webhook (/webhooks/stripe)...")
        try:
            resp = requests.post(f"{base_url}/webhooks/stripe", data=b"test_payload")
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.json()}")
        except Exception as e:
            print(f"FAILED: Could not connect to webhook: {e}")

    finally:
        print("\nStopping server...")
        process.terminate()
        try:
             # Wait for process to terminate, with a timeout to avoid hanging
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Process did not terminate gracefully, killing...")
            process.kill() # Force kill if it doesn't terminate
        
        # Capture any output
        stdout, stderr = process.communicate()
        if stdout: print(f"Server Stdout: {stdout.decode()}")
        if stderr: print(f"Server Stderr: {stderr.decode()}")

if __name__ == "__main__":
    verify_health()
