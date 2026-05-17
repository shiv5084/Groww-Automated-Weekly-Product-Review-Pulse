import uvicorn
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["PYTHONPATH"] = str(PROJECT_ROOT)

def main():
    print("Starting Groww Pulse API server...")
    print(f"Project Root: {PROJECT_ROOT}")
    
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    
    # Run uvicorn
    uvicorn.run(
        "src.phase6_api.app:app",
        host="127.0.0.1",
        port=10001,
        reload=True
    )

if __name__ == "__main__":
    main()
