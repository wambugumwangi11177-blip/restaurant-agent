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

def setup_backend_only():
    if not os.path.exists("backend"):
        os.makedirs("backend")
        print("Created backend directory.")
    
    # Create venv
    venv_path = os.path.join("backend", "venv")
    if not os.path.exists(venv_path):
        print("Creating Python virtual environment...")
        run_command(f"\"{sys.executable}\" -m venv {venv_path}")
    
    # Install dependencies
    print("Installing FastAPI and Uvicorn...")
    if os.name == 'nt':
        pip_cmd = os.path.join(venv_path, "Scripts", "pip")
    else:
        pip_cmd = os.path.join(venv_path, "bin", "pip")
        
    run_command(f"\"{pip_cmd}\" install fastapi uvicorn sentry-sdk python-dotenv python-jose[cryptography] passlib[argon2] python-multipart argon2-cffi")

    # Create main.py
    main_py_path = os.path.join("backend", "main.py")
    if not os.path.exists(main_py_path):
        with open(main_py_path, "w") as f:
            f.write("from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef read_root():\n    return {'Hello': 'World'}")
        print("Created backend/main.py")

if __name__ == "__main__":
    setup_backend_only()
