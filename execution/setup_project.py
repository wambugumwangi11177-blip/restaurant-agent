import os
import subprocess
import sys

def run_command(command, cwd=None):
    print(f"Running: {command}")
    try:
        # allow output to stream to stdout/stderr so we can see it in real-time (or at least when querying status)
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

def setup_frontend():
    if os.path.exists("frontend"):
        print("Frontend directory already exists. Skipping...")
        return

    print("Initializing Next.js Frontend...")
    # Using npx create-next-app with non-interactive flags
    cmd = "npx -y create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias \"@/*\""
    run_command(cmd)

def setup_backend():
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
    # We need to use the pip from the venv
    if os.name == 'nt':
        pip_cmd = os.path.join(venv_path, "Scripts", "pip")
    else:
        pip_cmd = os.path.join(venv_path, "bin", "pip")
        
    run_command(f"\"{pip_cmd}\" install fastapi uvicorn")

    # Create main.py
    main_py_path = os.path.join("backend", "main.py")
    if not os.path.exists(main_py_path):
        with open(main_py_path, "w") as f:
            f.write("from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef read_root():\n    return {'Hello': 'World'}")
        print("Created backend/main.py")

if __name__ == "__main__":
    setup_frontend()
    setup_backend()
    print("Project initialization complete.")
