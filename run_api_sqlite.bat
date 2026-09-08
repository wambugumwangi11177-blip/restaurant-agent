@echo off
cd /d "C:\Users\Administrator\restaurant-agent\restaurant-agent\backend"
set "DATABASE_URL=sqlite:///./dev_verify.db"
set "MPESA_ENV="
set "APP_ENV="
python main.py
