# SQLite User Authentication Design

## Goal

Add database-backed login to Panshi Trading AI. The current installation must
accept username `ylfego` and the configured password, while the repository
never stores the plaintext password or a reusable session token.

## Architecture

Authentication belongs to the FastAPI service because it already owns the
SQLite database. Next.js owns the login page and browser cookie, but it never
opens SQLite directly.

The browser sends credentials to a same-origin Next.js route. That route
forwards them to FastAPI with the existing private API bearer token. FastAPI
verifies the password, creates a random session token, stores only its SHA-256
digest, and returns the raw token once. Next.js stores the token in an
`HttpOnly`, `SameSite=Strict` cookie.

Next.js middleware validates the cookie through FastAPI before allowing access
to application pages or browser-facing API routes. `/login`, login/logout
routes, framework assets, and the application icon remain public.

## SQLite Schema

`users`:

- `user_id`: UUID primary key
- `username`: unique normalized username
- `password_hash`: encoded `scrypt` parameters, salt, and digest
- `is_active`: account status
- `created_at`, `updated_at`: audit timestamps

`auth_sessions`:

- `session_id`: UUID primary key
- `user_id`: owning user
- `token_hash`: unique SHA-256 digest of the browser token
- `created_at`, `expires_at`: absolute session lifetime

An Alembic migration creates both tables. Expired sessions are deleted during
login and session validation. The initial implementation uses a 12-hour
absolute lifetime.

## Password And Session Security

- Passwords use Python's `hashlib.scrypt` with a random per-user salt.
- Password verification uses `secrets.compare_digest`.
- Browser session tokens use at least 256 bits of randomness.
- Only token hashes are persisted.
- Authentication errors do not reveal whether a username exists.
- Cookies are `HttpOnly`, `SameSite=Strict`, scoped to `/`, and marked
  `Secure` outside local HTTP mode.
- Login and logout browser routes enforce the existing same-origin boundary.
- The FastAPI authentication endpoints remain protected by the server-side API
  bearer token and are not directly callable by an unauthenticated browser.

## Administration And Migration

A `panshi-user` CLI manages users against `TRADING_AGENT_DATABASE_URL`:

- `panshi-user set-password <username>` creates the user or replaces its
  password hash.
- `panshi-user disable <username>` disables the user and deletes its sessions.
- `panshi-user enable <username>` re-enables the user.

The password is read from an interactive prompt or standard input, never from a
command-line argument. The current machine will initialize `ylfego` after the
migration.

Moving to another server requires copying the SQLite database and image
storage, or running the same Alembic migrations and user CLI against a new
SQLite file. No source-code credential changes are required.

## User Experience

- Unauthenticated page requests redirect to `/login?next=<path>`.
- Unauthenticated browser API requests return `401` JSON instead of HTML.
- Successful login returns to the validated local `next` path or `/`.
- Failed login shows a generic error and keeps the username.
- The sidebar displays the current username and a logout action.
- Logout invalidates the database session, clears the cookie, and returns to
  `/login`.

## Failure Handling

- Missing authentication configuration fails closed.
- FastAPI unavailability redirects page requests to login with a service
  message and rejects API requests with `503`.
- Invalid, expired, disabled-user, or deleted sessions are treated as
  unauthenticated.
- Logout is idempotent even when the session is already invalid.

## Testing

- Unit tests cover password hashing, verification, and malformed hashes.
- Repository tests cover user upsert, disable/enable, session creation,
  expiry, revocation, and token hashing.
- API tests cover login success/failure, session validation, logout, disabled
  users, and API bearer protection.
- Migration tests verify both authentication tables.
- Local runtime tests verify required auth settings and CLI availability.
- Playwright covers redirect to login, correct and incorrect credentials,
  protected pages and APIs, tampered cookies, logout, safe `next` handling,
  and persistence across refresh.

