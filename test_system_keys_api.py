import httpx
import asyncio

BASE_URL = "http://localhost:18000/api"

async def test_api():
    async with httpx.AsyncClient() as client:
        print("1. Login as Admin...")
        resp = await client.post(f"{BASE_URL}/auth/token", data={
            "username": "admin",
            "password": "changeme"
        })
        if resp.status_code != 200:
            print(f"Login failed: {resp.text}")
            return
        
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Login successful!")

        print("\n2. Get System Keys...")
        resp = await client.get(f"{BASE_URL}/system-keys", headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Keys: {resp.json()}")

        print("\n3. Create System Key...")
        resp = await client.post(f"{BASE_URL}/system-keys", headers=headers, json={
            "raw_key": "sk-real-test-sys-key-001",
            "use_proxy": True,
            "is_active": True
        })
        print(f"Status: {resp.status_code}")
        new_key = resp.json()
        print(f"Created: {new_key}")
        
        if resp.status_code == 201:
            key_id = new_key["id"]
            
            print(f"\n4. Update System Key {key_id} (disable proxy)...")
            resp = await client.put(f"{BASE_URL}/system-keys/{key_id}", headers=headers, json={
                "use_proxy": False
            })
            print(f"Status: {resp.status_code}")
            print(f"Updated: {resp.json()}")

            print(f"\n5. Delete System Key {key_id}...")
            resp = await client.delete(f"{BASE_URL}/system-keys/{key_id}", headers=headers)
            print(f"Status: {resp.status_code}")

            print("\n6. Verify Deletion (Deactivation)...")
            resp = await client.get(f"{BASE_URL}/system-keys", headers=headers)
            keys = resp.json()
            deleted_key = next((k for k in keys if k["id"] == key_id), None)
            if deleted_key:
                print(f"Key status after delete: is_active={deleted_key['is_active']}")
            else:
                print("Key completely removed from list (unexpected behavior, usually it's just marked inactive).")

if __name__ == "__main__":
    asyncio.run(test_api())
