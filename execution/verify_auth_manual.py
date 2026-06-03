import requests
import random
import string

def verify_auth_manual():
    base_url = "http://localhost:8004"
    
    # Generate random user
    rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"user_{rand_str}@example.com"
    password = "secretpassword"
    tenant = f"Tenant_{rand_str}"
    
    print(f"Registering {email}...")
    try:
        resp = requests.post(f"{base_url}/auth/register", json={
            "email": email,
            "password": password,
            "tenant_name": tenant
        })
        print(f"Register Status: {resp.status_code}")
        if resp.status_code != 200:
            print("Response:", resp.text)
            return
        
        token = resp.json().get("access_token")
        print("got access token")
    except Exception as e:
        print(f"Register failed: {e}")
        return

    print("Logging in...")
    try:
        resp = requests.post(f"{base_url}/auth/login", data={
            "username": email,
            "password": password
        })
        print(f"Login Status: {resp.status_code}")
        if resp.status_code != 200:
            print("Response:", resp.text)
            return
    except Exception as e:
        print(f"Login failed: {e}")
        return

    print("Checking /auth/me...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{base_url}/auth/me", headers=headers)
        print(f"Me Status: {resp.status_code}")
        print("Response:", resp.json())
        
        if resp.status_code == 200 and resp.json().get("email") == email:
            print("SUCCESS: Auth Verified!")
        else:
            print("FAILED: /auth/me check failed")
    except Exception as e:
        print(f"Me check failed: {e}")

if __name__ == "__main__":
    verify_auth_manual()
