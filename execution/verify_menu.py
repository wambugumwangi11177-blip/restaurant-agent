import requests
import random
import string

def verify_menu():
    base_url = "http://localhost:8005"
    
    # 1. Register/Login as Admin
    rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    email = f"admin_{rand_str}@example.com"
    password = "secretpassword"
    tenant = f"Tenant_{rand_str}"
    
    print(f"Registering Admin {email}...")
    try:
        resp = requests.post(f"{base_url}/auth/register", json={
            "email": email,
            "password": password,
            "tenant_name": tenant
        })
        if resp.status_code != 200:
            print("Register Failed:", resp.text)
            return
        token = resp.json().get("access_token")
    except Exception as e:
        print(f"Auth failed: {e}")
        return

    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Create Menu Item
    print("Creating Menu Item...")
    item_data = {
        "name": "Cheeseburger",
        "price": 1200, # 12.00
        "category": "Main"
    }
    resp = requests.post(f"{base_url}/menu/", json=item_data, headers=headers)
    print(f"Create Status: {resp.status_code}")
    print("Response:", resp.json())
    
    if resp.status_code != 200:
        print("Failed to create item")
        return
        
    item_id = resp.json().get("id")
    
    # 3. List Menu Items
    print("Listing Menu Items...")
    resp = requests.get(f"{base_url}/menu/", headers=headers)
    print(f"List Status: {resp.status_code}")
    items = resp.json()
    print(f"Found {len(items)} items")
    
    # 4. Update Menu Item
    print(f"Updating Item {item_id}...")
    update_data = {"price": 1300}
    resp = requests.put(f"{base_url}/menu/{item_id}", json=update_data, headers=headers)
    print(f"Update Status: {resp.status_code}")
    print("Response:", resp.json())
    
    # 5. Delete Menu Item
    print(f"Deleting Item {item_id}...")
    resp = requests.delete(f"{base_url}/menu/{item_id}", headers=headers)
    print(f"Delete Status: {resp.status_code}")
    
    # Verify Deletion
    resp = requests.get(f"{base_url}/menu/", headers=headers)
    items = resp.json()
    found = any(i['id'] == item_id for i in items)
    if not found:
        print("SUCCESS: Item deleted and verified.")
    else:
        print("FAILED: Item still exists.")

if __name__ == "__main__":
    verify_menu()
