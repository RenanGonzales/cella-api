# Security

Cella runs as a public portfolio demo. Authentication is deliberately simple, but every shortcut below is a conscious trade-off, listed with what would change before running Cella as a real product.

Format: **threat -> protection -> trade-off**.

## What is implemented

| Threat | Protection | Where |
|---|---|---|
| Stolen password database | Passwords hashed with bcrypt (salted, slow by design); plain passwords are never stored or logged | `app/core/security.py` |
| Silent password truncation | bcrypt ignores everything after 72 bytes. Instead of accepting a password that is only partly checked, longer passwords are rejected with a clear error | `app/schemas/auth.py` |
| Weak passwords | Minimum of 8 characters | `app/schemas/auth.py` |
| User enumeration by error message | Login returns the same `401 Invalid email or password` for an unknown email and for a wrong password | `app/api/routes/auth.py` |
| User enumeration by response time | When the email does not exist, a dummy bcrypt check still runs, so both failures take about the same time | `app/core/security.py` |
| Forged or tampered tokens | JWT signed with HS256; signature, expiry and required claims are verified on every request | `app/core/security.py` |
| Weak signing key in production | The API refuses to start in production with the default secret or a secret shorter than 32 bytes (RFC 7518) | `app/core/config.py` |
| One household reading another's data | Every protected route resolves the user from the token (`get_current_user`) and filters by `household_id`. Ids are random UUIDs, not sequential numbers | `app/api/deps.py` |
| Insecure direct object references (IDOR) | Every id in a URL or in a request body (category, storage area) is checked against the user's household. Rows of another household answer `404`, never `403`, so their existence is not even confirmed. Covered by tests | `app/services/catalog.py` |
| Undoing someone else's action | Undo only works for the person who consumed, within 10 minutes; other members get `403`, other households `404` | `app/services/shopping.py` |
| Lost updates under concurrent requests | Stock changes lock the product row, so simultaneous requests cannot overwrite each other | `app/services/shopping.py` |
| Guessable invite codes | 8 random characters from a 31-symbol alphabet (about 850 billion combinations), generated with `secrets` | `app/domain/invite.py` |
| Duplicate accounts | Emails are normalized to lowercase and enforced unique by the database, including concurrent sign-ups | `app/api/routes/auth.py` |
| Demo login abused outside the demo | `POST /auth/demo` only exists when `DEMO_ENABLED=true` | `app/api/routes/auth.py` |
| Demo visitors seeing each other's data | Each visitor gets a private copy of the demo household; the usual household scoping (`404` across households) keeps copies apart | `app/services/demo.py` |
| Demo copies filling the database | Copies expire after 24 hours and are deleted on the next demo (or by `scripts/cleanup_demo.py`); at most `DEMO_MAX_SANDBOXES` live copies, then `503` | `app/services/demo.py` |
| Real accounts inside a temporary demo | Invite codes of demo copies are rejected at sign-up | `app/api/routes/auth.py` |
| Cross-origin requests | CORS only allows the local dev frontend; in production the frontend and the API share one origin | `app/main.py` |

## Known trade-offs (demo mode)

- **Token in `localStorage`.** Simple for the frontend, but any XSS bug could read it.
- **One long-lived token (7 days), no server-side sessions.** A leaked token stays valid until it expires, and logout only deletes the token on the device.
- **No rate limiting on login or on new demos.** Password guessing is only slowed down by bcrypt's cost, and new demos only by the cap on live copies. In production, Nginx `limit_req` covers both until the API has its own limiter.
- **No email verification or password reset.** Anyone can sign up with any email address.

## Production roadmap

What would change before taking Cella out of demo mode, in order of priority:

1. **httpOnly cookie + CSRF token** instead of `localStorage`. JavaScript can no longer read the session, which neutralizes token theft through XSS. `SameSite=Strict` plus a CSRF header closes the gap that cookies open.
2. **Short access token + server-side sessions with refresh token rotation.** Access tokens of ~15 minutes, refresh tokens stored hashed in a `sessions` table and replaced on every use. Enables real logout, "log out of all devices", and detects a reused (stolen) refresh token.
3. **Rate limiting** on login and sign-up (for example, 5 attempts per minute per IP and per account), returning `429`.
4. **Sign in with Google (OAuth 2.0 / OpenID Connect).** Fewer passwords to manage; `password_hash` becomes optional and a `google_id` column is added.
5. **Email verification, password reset and optional 2FA (TOTP).**
6. **Security headers at the proxy** (HSTS, Content-Security-Policy, X-Content-Type-Options), configured in Nginx.
