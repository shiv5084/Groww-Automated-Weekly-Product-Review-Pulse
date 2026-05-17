import requests
import time
import sys

def test_api_e2e():
    base_url = "http://127.0.0.1:10001"
    
    print("Step 1: Checking Health...")
    try:
        resp = requests.get(f"{base_url}/health")
        print(f"Health check status: {resp.status_code}")
        print(f"Response: {resp.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        sys.exit(1)

    print("\nStep 2: Triggering E2E Pipeline (Dry Run)...")
    # Using weeks=1 to make it faster
    try:
        resp = requests.post(
            f"{base_url}/run",
            params={"dry_run": True, "weeks": 1, "scrape": True}
        )
        print(f"Trigger status: {resp.status_code}")
        print(f"Response: {resp.json()}")
    except Exception as e:
        print(f"Trigger failed: {e}")
        sys.exit(1)

    print("\nStep 3: Monitoring background run (check server console logs)...")
    print("The pipeline will run in the background. Check the terminal where uvicorn is running.")

if __name__ == "__main__":
    test_api_e2e()
