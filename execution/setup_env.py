import os

def create_env_file(path, content):
    if os.path.exists(path):
        print(f"Skipping {path}: File already exists.")
        return
    
    with open(path, "w") as f:
        f.write(content)
    print(f"Created {path}")

def setup_env():
    # Frontend .env.local
    frontend_env = """# Frontend Environment Variables
NEXT_PUBLIC_API_URL=http://localhost:8000
"""
    if os.path.exists("frontend"):
        create_env_file(os.path.join("frontend", ".env.local"), frontend_env)
    else:
        print("Error: frontend directory not found.")

    # Backend .env
    backend_env = """# Backend Environment Variables
DATABASE_URL=postgresql://user:password@localhost/restaurant_db
OPENAI_API_KEY=your_openai_api_key_here
SECRET_KEY=your_secret_key_here
"""
    if os.path.exists("backend"):
        create_env_file(os.path.join("backend", ".env"), backend_env)
    else:
        print("Error: backend directory not found.")

if __name__ == "__main__":
    setup_env()
