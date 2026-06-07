# Deployment Guide for Restaurant Agent Backend

## Prerequisites
- [Railway CLI](https://railway.app/cli) installed (or use Railway dashboard)
- [Neon](https://neon.tech) account with a PostgreSQL database
- Git repository pushed to GitHub (or Railway can deploy from local)

## Step 1: Set Environment Variables
Obtain the following values:

1. **DATABASE_URL** – Neon PostgreSQL connection string (format: `postgresql://user:password@host/dbname`)
2. **SECRET_KEY** – A strong random string for JWT signing (generate with `openssl rand -hex 32`)
3. **OPENAI_API_KEY** – Your OpenAI API key (if using AI features)
4. **CORS_ORIGINS** – Comma-separated list of allowed origins (e.g., `https://your-frontend.vercel.app,http://localhost:3000`)
5. **PORT** – Railway sets this automatically; keep the start command as `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Step 2: Configure Railway
### Option A: Using Railway CLI
```bash
# Login to Railway
railway login

# Link to existing project or create new
railway init   # if starting new
railway up     # deploy

# Set environment variables
railway variables set DATABASE_URL="your_neon_connection_string"
railway variables set SECRET_KEY="your_generated_secret"
railway variables set OPENAI_API_KEY="your_openai_key"
railway variables set CORS_ORIGINS="https://your-frontend.vercel.app"
```

### Option B: Using Railway Dashboard
1. New Project → Deploy from GitHub repo (or Dockerfile)
2. Go to Settings → Variables and add the above key/value pairs.
3. Ensure the build command is: `pip install -r requirements.txt`
4. Ensure the start command is: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Step 3: Run Migrations & Seed Data
After deployment, run one-off commands on Railway:

```bash
# Open a shell on the deployed service
railway shell

# Inside the container:
alembic upgrade head
python populate_lavy.py
exit
```

## Step 4: Verify Deployment
Test the health endpoint:
```bash
curl https://your-backend.up.railway.app/health
# Should return {"status":"ok"} or similar
```

Test login:
```bash
curl -X POST https://your-backend.up.railway.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"lavy@leviii.ai","password":"lavy123"}'
```
Should return a JWT token.

## Step 5: Configure Vercel Frontend
In your Vercel project Settings → Environment Variables:
- `NEXT_PUBLIC_API_URL` = `https://your-backend.up.railway.app`
- (Optional) any other API keys the frontend needs.

Redeploy the frontend.

## Troubleshooting
### "Incorrect email or password"
1. Verify the backend you’re pointing at is the one you seeded (check with `/api/v1/auth/me` using a token from login).
2. Ensure `SECRET_KEY` matches between token generation and validation (if you redeployed with a new SECRET_KEY, old tokens become invalid).
3. Ensure the database has the `lavy@leviii.ai` user:
   ```bash
   railway run psql $DATABASE_URL -c "SELECT email FROM users WHERE email='lavy@leviii.ai';"
   ```
4. Check that the password hash in the DB matches `get_password_hash("lavy123")` from the code.

### CORS Errors
Ensure `CORS_ORIGINS` includes your Vercel frontend URL (including preview deployments if needed).

### Missing Modules
Ensure `requirements.txt` includes all dependencies (e.g., `slowapi`, `apscheduler`, `python-jose[cryptography]`, etc.).

## Files in this repo
- `Dockerfile` – for containerized deployment
- `railway.json` – Railway project configuration
- `render.yaml` – Render alternative
- `Procfile` – for Heroku-like platforms
- `runtime.txt` – Python version
- `requirements.txt` – Python dependencies

## Next Steps
If you encounter issues, share:
- The backend URL you’re testing
- Output of `curl -v` to the login endpoint
- Any logs from the deployment platform (Railway/Neon/Vercel)
Then we can diagnose further.