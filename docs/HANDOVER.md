# Handing over Eleven sign-ins (plain guide)

This is for **Wambugu** or the **owner** — no developer needed.

## What “reset sign-in” means

Each person (owner, Jack, accountant) has their own email and password. When you **reset sign-in** for someone:

1. Their old password **stops working** immediately.
2. They get a **one-time 6-digit code** (valid for **72 hours**).
3. You **give them the code in person** or on a phone call — not by public chat.
4. They open the app, sign in with their email, enter the **code** and a **new password** they choose.

## Reset a login (owner app)

1. Sign in as **owner** on the **live** or **test** site (see below).
2. Open **Settings** → **Logins**.
3. Find the person (owner, Jack, or accountant).
4. Tap **Reset sign-in** → confirm.
5. Copy the **6-digit code** and hand it to that person. **It is shown only once.**

If you reset **your own** owner login, you will be signed out — that is normal when handing the business to the real owner.

## Install the app (APK)

1. Open the install link you were given (or download the APK from your team).
2. Allow “Install from unknown sources” if Android asks.
3. Open **LEVIII** and sign in.

**Jack’s store APK** is for the storekeeper only (`jack@eleven.leviii`).

## Test site vs live site

| | **Test** | **Live** |
|---|----------|----------|
| Use for | Trying Jack, photos, bills | Real Eleven day-to-day |
| Data | Can be wiped/re-seeded | Keep this clean |
| URLs | Your team’s staging URL | Your production URL |

Use **test** to practice reset + code + new password before doing it on **live**.

## Forgot password?

There is **no email “forgot password”** link in the app (email is not always set up).

**Do this instead:**

1. Someone who is already **owner** (or your platform admin) resets that login in **Settings → Logins**.
2. Hand over the new **6-digit code**.
3. That person sets a **new password** on the sign-in screen.

If the owner is locked out and no one can sign in, contact your **platform admin** — they can reset any Eleven login.

## Tips

- Treat the 6-digit code like a house key: show it only to the right person.
- After 72 hours, generate a **new reset** if they did not finish in time.
- Each person should pick a **strong password** they will remember (letters and numbers, at least 8 characters).