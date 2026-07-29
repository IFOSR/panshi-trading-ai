# SQLite User Authentication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SQLite-backed users and sessions, protect the Panshi web UI, initialize `ylfego`, and publish the completed application to GitHub without committing credentials.

**Architecture:** FastAPI owns password verification and session persistence in the existing SQLite database. Next.js proxies authentication, stores an opaque `HttpOnly` cookie, and asks FastAPI to validate it in middleware before serving protected pages or API routes.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy, Alembic, `hashlib.scrypt`, Next.js 15 middleware and route handlers, React 19, Playwright, pytest.

---

### Task 1: Password And Session Primitives

**Files:**
- Create: `src/trading_agent/auth/__init__.py`
- Create: `src/trading_agent/auth/passwords.py`
- Create: `src/trading_agent/auth/tokens.py`
- Create: `tests/auth/test_passwords.py`
- Create: `tests/auth/test_tokens.py`

**Step 1: Write failing tests**

Cover password hash round trips, random salts, wrong passwords, malformed
hashes, random session token generation, and SHA-256 token digests.

**Step 2: Verify RED**

Run:

```bash
pytest -q tests/auth/test_passwords.py tests/auth/test_tokens.py
```

Expected: collection fails because `trading_agent.auth` does not exist.

**Step 3: Implement minimal primitives**

Use an encoded format containing the scrypt work parameters, URL-safe salt,
and digest. Reject malformed or unsupported encodings without raising during
normal login verification.

**Step 4: Verify GREEN**

Run the same pytest command and expect all tests to pass.

**Step 5: Commit**

```bash
git add src/trading_agent/auth tests/auth
git commit -m "feat(auth): add password and session primitives"
```

### Task 2: SQLite Authentication Persistence

**Files:**
- Modify: `src/trading_agent/db/models.py`
- Modify: `src/trading_agent/db/repositories.py`
- Create: `src/trading_agent/auth/repository.py`
- Create: `alembic/versions/0004_user_authentication.py`
- Create: `tests/auth/test_repository.py`
- Modify: `tests/db/test_migrations.py`

**Step 1: Write failing repository and migration tests**

Cover user creation and password replacement, username normalization, account
enable/disable, random session creation, token hash persistence, expiration,
validation, logout, and session removal when disabling a user.

**Step 2: Verify RED**

```bash
pytest -q tests/auth/test_repository.py tests/db/test_migrations.py
```

Expected: authentication models and migration are missing.

**Step 3: Implement models, repository, and migration**

Create `users` and `auth_sessions` tables. Keep authentication operations in a
dedicated repository so the trading case repository remains decoupled.

**Step 4: Verify GREEN**

Run the same pytest command and expect all tests to pass.

**Step 5: Commit**

```bash
git add src/trading_agent/db src/trading_agent/auth/repository.py alembic/versions/0004_user_authentication.py tests/auth/test_repository.py tests/db/test_migrations.py
git commit -m "feat(auth): persist users and sessions in SQLite"
```

### Task 3: FastAPI Authentication Contract

**Files:**
- Create: `src/trading_agent/auth/service.py`
- Modify: `src/trading_agent/api/app.py`
- Create: `tests/api/test_auth_flow.py`

**Step 1: Write failing API tests**

Cover:

- valid login returns a raw session token once;
- invalid username and invalid password return the same `401`;
- session validation returns the authenticated username;
- expired, malformed, and disabled-user sessions return `401`;
- logout removes the session and is idempotent;
- every auth endpoint still requires the private API bearer token.

**Step 2: Verify RED**

```bash
pytest -q tests/api/test_auth_flow.py
```

Expected: `/v1/auth/*` routes return `404`.

**Step 3: Implement the service and endpoints**

Add:

- `POST /v1/auth/login`
- `GET /v1/auth/session`
- `POST /v1/auth/logout`

Accept session tokens through `X-Panshi-Session`. Never include password hashes
or token hashes in API responses.

**Step 4: Verify GREEN**

Run the auth API tests and the existing API suite.

**Step 5: Commit**

```bash
git add src/trading_agent/auth/service.py src/trading_agent/api/app.py tests/api/test_auth_flow.py
git commit -m "feat(auth): expose authenticated session API"
```

### Task 4: User Administration And Local Runtime

**Files:**
- Create: `src/trading_agent/auth/cli.py`
- Modify: `pyproject.toml`
- Modify: `src/trading_agent/local_runtime.py`
- Modify: `tests/deployment/test_local_runtime.py`
- Create: `tests/auth/test_cli.py`
- Modify: `.env.local.example`

**Step 1: Write failing CLI and runtime tests**

Cover password input through stdin, create/update, enable, disable, invalid
commands, database migration prerequisite, and installation of `panshi-user`.

**Step 2: Verify RED**

```bash
pytest -q tests/auth/test_cli.py tests/deployment/test_local_runtime.py
```

Expected: the CLI and auth runtime settings are missing.

**Step 3: Implement CLI and runtime contract**

Add `panshi-user set-password`, `enable`, and `disable`. The CLI must read the
password from `getpass` or `--password-stdin`; it must not accept a password
argument. Add a random local authentication proxy secret only if required by
the final web boundary, never a user password.

**Step 4: Verify GREEN**

Run the same tests and `panshi-user --help`.

**Step 5: Commit**

```bash
git add src/trading_agent/auth/cli.py pyproject.toml src/trading_agent/local_runtime.py tests/deployment/test_local_runtime.py tests/auth/test_cli.py .env.local.example
git commit -m "feat(auth): add SQLite user administration"
```

### Task 5: Next.js Login, Cookie, And Route Protection

**Files:**
- Create: `web/lib/auth.ts`
- Create: `web/app/login/page.tsx`
- Create: `web/components/login-form.tsx`
- Create: `web/app/api/auth/login/route.ts`
- Create: `web/app/api/auth/logout/route.ts`
- Create: `web/app/api/auth/session/route.ts`
- Modify: `web/middleware.ts`
- Modify: `web/components/conversation-sidebar.tsx`
- Modify: `web/app/globals.css`

**Step 1: Write failing Playwright authentication tests**

Cover unauthenticated redirects, protected API `401`, successful login,
incorrect password, safe handling of `next`, refresh persistence, tampered
cookies, logout, and sidebar username display.

**Step 2: Verify RED**

```bash
cd web
npx playwright test tests/auth.spec.ts
```

Expected: `/login` and auth routes do not exist and protected pages remain
public.

**Step 3: Implement browser authentication**

Use cookie name `panshi_session`. Middleware must distinguish page navigation
from browser API requests, validate through FastAPI, and fail closed when
authentication configuration or FastAPI is unavailable.

**Step 4: Verify GREEN**

Run the auth Playwright tests and `npm run lint`.

**Step 5: Commit**

```bash
git add web/lib/auth.ts web/app/login web/components/login-form.tsx web/app/api/auth web/middleware.ts web/components/conversation-sidebar.tsx web/app/globals.css web/tests/auth.spec.ts
git commit -m "feat(web): require database-backed login"
```

### Task 6: Preserve Existing End-To-End Coverage

**Files:**
- Modify: `web/tests/api-server.mjs`
- Create: `web/tests/auth.setup.ts`
- Modify: `web/playwright.config.ts`
- Modify: `web/tests/strategy-console.spec.ts`

**Step 1: Add authenticated fixture behavior**

The fixture API must implement login, session validation, and logout without
weakening existing API token checks.

**Step 2: Configure authenticated storage state**

Create a setup project that logs in once with test-only credentials. Existing
strategy tests depend on that project. Authentication tests clear cookies when
they need an unauthenticated browser.

**Step 3: Run full Playwright**

```bash
cd web
npm run test:e2e
```

Expected: all prior tests and all new auth tests pass.

**Step 4: Commit**

```bash
git add web/tests web/playwright.config.ts
git commit -m "test(web): run strategy flows behind authentication"
```

### Task 7: Initialize The Current SQLite User And Document Operations

**Files:**
- Modify: `docs/runbook.md`
- Modify: `.env.example`

**Step 1: Update documentation tests or assertions**

Require the runbook to explain first-user creation, password rotation, session
expiry, logout, server migration, SQLite backup, and recovery.

**Step 2: Update documentation**

Remove the obsolete “no login” statement. Document:

```bash
.local/venv/bin/panshi-user set-password <username>
```

Use the actual username `ylfego` when initializing the current machine.

**Step 3: Initialize the current machine**

Run migrations, then pass the requested password through standard input to
create or update `ylfego`. Verify the database contains the username and a
password hash, not plaintext.

**Step 4: Restart and smoke test**

```bash
./trading-agent.sh restart
./bin/trading-agent-local status
```

Use a browser to verify login, refresh, logout, wrong password, and successful
login again on port `8989`.

**Step 5: Commit**

```bash
git add docs/runbook.md .env.example
git commit -m "docs: document SQLite user authentication"
```

### Task 8: Full Verification And GitHub Publication

**Files:**
- Modify: `.gitignore`
- No production behavior changes unless verification finds a defect.

**Step 1: Exclude generated artifacts**

Ensure `web/tmp/`, runtime data, SQLite files, logs, cookies, storage state, and
all local environment files are ignored.

**Step 2: Run full verification**

```bash
pytest -q
ruff check .
mypy src/trading_agent
cd web && npm run lint && npm run build && npm run test:e2e
git diff --check
```

**Step 3: Review staged content for secrets**

Search staged content for the requested plaintext password, API keys, local
tokens, `.local` paths, and Playwright cookies. The requested password must
not appear in the committed diff.

**Step 4: Commit the complete current application**

Stage the complete source, tests, migrations, scripts, and documentation while
excluding generated artifacts. Use a conventional commit that reflects the
full current product state if earlier work remains uncommitted.

**Step 5: Create and push GitHub repository**

If no remote has been configured, create the approved private GitHub
repository under the authenticated account, add `origin`, and push
`codex/trading-agent` without force.
