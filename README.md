# Taxcart client portal

Clients sign in and see their sales and the tax collected on them, country by country, with the US state by state. Staff set up each client: where the sales come from, which countries they report, and who can sign in.

## How it fits together

```
Browser --> Portal (this repo) --> Tax engine --> Shopify data in Postgres
            logins, clients,       /reports/summary
            countries
```

- The browser only ever talks to the portal. The portal checks who is asking, then calls the tax engine server-side with the internal key.
- A client sees only their own companies. Staff see every client, plus a "For review" section with items the tax team should look at.
- The portal has its own database for logins and settings. It holds no order data.

## What is in phase 1

| Area | Status |
|---|---|
| Email and password sign-in, forced password change at first sign-in | Built |
| Staff screen: add a client, connect a Shopify store, choose countries, add and manage logins | Built |
| Sales & tax report by country, by state for chosen countries, by tax type and rate | Built |
| Sales file upload | Not built yet (phase 2) |
| Zamp filings and registrations | Not built yet (phase 3) |

## Folder map

| Path | What it is |
|---|---|
| `main.py` | Entry point |
| `portal/app.py` | Endpoints: sign-in, session, report, staff setup |
| `portal/security.py` | Password hashing, session tokens, sign-in throttling |
| `portal/engine.py` | Calls the tax engine and shapes its report for the page |
| `portal/db.py` | Database tables (created automatically at start) |
| `portal/config.py` | Settings read from environment variables |
| `public/` | The pages: `index.html`, `styles.css`, `js/app.js` (screens), `js/format.js` (display), `js/api.js` (endpoint client) |
| `tests/test_portal.py` | 27 tests |

## Deploying on Render

1. **Database.** Create a new Neon project (for example `taxcart-portal`) in the same region as the engine. Copy its connection string.
2. **Web service.** In Render: New > Web Service > this repo.
   - Language: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Region: same as the engine
3. **Environment variables.**

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | The Neon connection string from step 1 |
   | `TAX_ENGINE_URL` | `https://tax-engine-ysr4.onrender.com` |
   | `TAX_ENGINE_KEY` | The engine's `INTERNAL_KEY` |
   | `APP_ORIGIN` | The portal's own address, for example `https://taxcart-portal.onrender.com` (no trailing slash) |
   | `BOOTSTRAP_ADMIN_EMAIL` | Your email |
   | `BOOTSTRAP_ADMIN_PASSWORD` | A password of 12 or more characters, used once |

4. **First sign-in.** Open the portal, sign in with the bootstrap email and password, and choose a new password when asked. Then delete the two `BOOTSTRAP_` variables in Render. They are ignored once any login exists.
5. **Add a client.** Clients > Add a client. Enter the store's `myshopify.com` address, add the countries, tick "By state or region" where needed (the US is ticked for you), and Save. Then add a login: the portal shows a temporary password once, which you pass to the client.

The store must already be installed on the Taxcart Shopify app, so the engine holds its orders.

## Running the tests

They need a Postgres database they can wipe:

```
pip install -r requirements.txt pytest httpx
TEST_DATABASE_URL=postgresql://user@host/empty_db pytest
```

## How sign-in is protected

- Passwords are stored as scrypt hashes. Temporary passwords are shown once and never stored in readable form.
- The session is an HttpOnly, SameSite cookie. Only a hash of it is stored.
- Five wrong passwords in 15 minutes locks that address for the rest of the window.
- Every change must carry a header that a form on another website cannot send, and a matching Origin.
- A wrong email and a wrong password get the same answer.
- Changing or resetting a password signs that person out everywhere.

## Things to know

- **There is no "forgot password" email.** Staff reset a client's password from the Clients screen. Email would be needed to do it self-service.
- **Staff logins are created only by the bootstrap step.** A second staff login, or a forgotten staff password, currently needs a change in the database.
- **Lockout can be abused.** Someone who knows a client's email can lock them out for up to 15 minutes by guessing wrong passwords.
- **Amounts are in the store's currency** and are not converted.
- **Periods are UTC days**, not the store's timezone.
- **Tax collected by a marketplace** is included in the figures and marked where it applies.
- **Taxable sales are worked back from tax collected**, so they can differ from net sales by a few cents.
- **The first report after a quiet spell is slow** while the engine wakes up on free hosting.
