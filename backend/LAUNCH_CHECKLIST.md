# Launch Checklist — Leviii AI

The steps that require **your accounts** and cannot be done from the codebase.
Everything here was flagged in `HARDENING_STATUS.md` as "needs YOU"; this is the
runnable version, in the order that matters.

Work top to bottom. Steps 1–3 are security-critical: until they're done, either
the app refuses to boot in production (by design) or a payment endpoint is
forgeable.

---

## 1. Generate and set the production secrets

Two values must be long, random, and never reused between environments.

```bash
# Run locally — do NOT commit the output anywhere.
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python -c "import secrets; print('MPESA_CALLBACK_TOKEN=' + secrets.token_urlsafe(32))"
```

Set both on Railway (service → **Variables**).

**Why `MPESA_CALLBACK_TOKEN` is not optional.** The M-Pesa settlement callback is
authenticated *only* by a secret embedded in its URL path
(`POST /webhooks/mpesa/{token}`). Without it, anyone who can guess a
`CheckoutRequestID` can forge a "payment received" and mark an order paid.
`startup_checks.py` treats a missing token as a **hard** problem and refuses to
boot when `MPESA_ENV=production` — that failed deploy is the intended behaviour,
not a bug.

> **Rotating it later:** the token is part of the callback URL, so changing it
> means updating `MPESA_CALLBACK_URL` *and* re-registering that URL with
> Safaricom. Changing one without the other silently drops every payment
> confirmation — orders stay unpaid with no error anywhere. See §5.

## 2. Set the remaining production env vars

| Variable | Value | Notes |
|---|---|---|
| `APP_ENV` | `production` | Turns on fail-closed startup checks |
| `MPESA_ENV` | `production` | Also turns them on — real money is moving |
| `CORS_ORIGINS` | your exact Vercel URL(s), comma-separated | No trailing slash. The built-in fallback list is a dev net, not a production ACL |
| `MPESA_CALLBACK_URL` | `https://<railway-domain>/webhooks/mpesa/<token from §1>` | Must match what Safaricom has registered |
| `DATABASE_URL` | from Neon/Railway | |
| `SENTRY_DSN` | from Sentry | Optional but see §4 |
| `LOG_FORMAT` | `json` | |

**Verify it actually took effect.** Env vars that look right in the dashboard and
aren't in the running process are the classic deploy failure. After deploying,
log in as an admin and hit:

```
GET /health/config
```

It reports `ready` / `degraded` / `blocked`, plus which integrations are live.
Admin-only, and it reports presence only — never values. Fix anything under
`blocking_problems` before taking real payments.

## 3. Database backups + one restore drill

Full steps in [`DISASTER_RECOVERY.md`](./DISASTER_RECOVERY.md).

- [ ] Enable automated Postgres backups (Neon/Railway console)
- [ ] Note the retention window and the RPO it implies
- [ ] **Run one restore into a scratch database** and confirm the order count matches

The drill is the part people skip. A backup you have never restored is a
hypothesis, not a backup — and the first time you test it should not be the day
you need it.

## 4. Monitoring

- [ ] **UptimeRobot** (or equivalent) on `GET /health` — 5-minute interval
- [ ] **Sentry** alert rule: notify on any new issue in production
- [ ] Optional: a second UptimeRobot check on `GET /health/db`, which fails
      independently of the app process when the database is unreachable

Without these, the failure mode is a customer telling you the system is down.

## 5. The three silent-breakage points

None of these raise an error. Each just quietly stops working, and you find out
from a confused restaurant owner.

1. **Safaricom `CallBackURL`** — registered on Safaricom's side, not yours.
   Changing the Railway domain or the callback token without re-registering
   means STK pushes still succeed and confirmations never arrive. Orders sit
   unpaid forever.
2. **Twilio webhook** — the WhatsApp inbound URL is configured in the Twilio
   console. If it points at a stale domain, the owner's messages vanish with no
   error on either side.
3. **`CORS_ORIGINS`** — if it doesn't exactly match the deployed frontend
   origin, every API call fails in the browser only. The backend looks perfectly
   healthy in logs and to any curl you run.

After **any** domain change, re-check all three.

## 6. GitHub branch protection

On `master`: require a pull request, require CI green before merge.

Repo → Settings → Branches → Add rule. This is the one item here with no
technical dependency — it takes about a minute and it is the only thing standing
between a tired late-night push and production.

## 7. Before the first real restaurant

- [ ] Enter their menu with **cost prices** (or better, recipes — see below)
- [ ] Build recipes via `PUT /menu/{id}/recipe` for the ingredients worth
      tracking: expensive, theft-prone, or fast-moving. A partial recipe book is
      fine and expected — nobody maps a bottled soda.
- [ ] Set opening stock counts (`POST /inventory/{id}/receive`)
- [ ] Add staff with hourly rates so labor cost % and ROI use real wages instead
      of the `DEFAULT_HOURLY_RATE_CENTS` fallback
- [ ] Set `Restaurant.owner_phone` so the 07:00 EAT briefing has somewhere to go
- [ ] Record their first payment (`POST /billing/record-payment`) — new tenants
      start on a 14-day trial and lose `/ai/*` when it lapses

Recipes are worth doing properly: with them, `cost_price` is derived from
ingredient costs rather than typed, so when a supplier raises chicken 15% every
affected dish's margin updates by itself and pricing flags the ones that just
fell through the floor. Without them it's a number someone typed once.

## 8. Known gaps to brief the restaurant on

Be straight about these up front rather than having them discovered mid-service:

- **No offline mode.** `sw.js` caches the app shell but deliberately skips
  `/api`, so orders cannot be taken without a connection. The documented
  fallback is paper, entered afterwards. Do not describe the POS as
  offline-capable.
- **Stock can go negative.** That's intentional — a sale is never blocked by a
  disagreeing count. A negative number means the opening count was wrong, and
  it's a signal to recount, not an error.
- **Single gunicorn worker.** Correct today (the rate limiter is in-process
  memory), but it caps throughput. Raising it requires Redis-backed rate
  limiting *and* moving the APScheduler jobs out of the web process — otherwise
  every restaurant gets a duplicate morning briefing for each worker.
