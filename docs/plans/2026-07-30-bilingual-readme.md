# Bilingual README Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a bilingual root README that explains the logical architecture and lets a new operator deploy, configure accounts, validate, and maintain Panshi Trading AI without consulting another document.

**Architecture:** Keep one GitHub-renderable Markdown file with a language selector linking to complete Chinese and English sections. Add a lightweight documentation contract test so language anchors, architecture boundaries, supported local-runtime commands, SQLite account administration, safety constraints, and persistent paths cannot silently disappear.

**Tech Stack:** GitHub Markdown, Mermaid, pytest, POSIX shell commands, Python local runtime, Next.js, FastAPI, SQLite.

---

### Task 1: Add the README documentation contract

**Files:**
- Create: `tests/deployment/test_readme.py`
- Test: `tests/deployment/test_readme.py`

**Step 1: Write the failing tests**

Add tests that require:

- A root `README.md`.
- Top-level links to `#中文` and `#english`.
- Complete Chinese and English headings.
- A Mermaid logical architecture diagram.
- The supported local-runtime architecture: browser, Next.js, FastAPI, SQLite,
  original image storage, Codex, free market data, strategy registry, strategy
  plugin, and risk engine.
- Explicit statements that OpenCV/local OCR are not in the production evidence
  path and that the language model cannot independently decide the action.
- The exact initialization, doctor, SQLite user creation, start, stop, restart,
  and status commands.
- The SQLite database, image, and log paths.
- `CODE_CLI_API_KEY`, optional TqSdk credentials, and the AkShare fallback.
- Account rotation, disable, enable, backup, restore, and migration guidance.
- The local URLs for Web and API documentation.
- The order-execution safety boundary.

**Step 2: Run the tests to verify they fail**

Run:

```sh
pytest -q tests/deployment/test_readme.py
```

Expected: FAIL because `README.md` does not exist.

**Step 3: Commit only after the README makes the contract pass**

Do not commit the failing test independently; keep the repository usable and
commit the test with the README implementation.

### Task 2: Write the bilingual README

**Files:**
- Create: `README.md`
- Reference: `docs/runbook.md`
- Reference: `.env.local.example`
- Reference: `src/trading_agent/local_runtime.py`
- Reference: `web/package.json`

**Step 1: Add the language selector**

Use stable explicit anchors:

```html
<a id="language"></a>

# Panshi Trading AI / 磐石交易AI

[中文](#中文) | [English](#english)
```

Each language section includes a link back to `#language`.

**Step 2: Add the Chinese section**

Write a complete Chinese document containing:

- Product positioning and safety boundary.
- Feature highlights.
- Mermaid logical architecture.
- Component responsibilities and trust chain.
- Screenshot-to-decision data flow.
- Detailed macOS/Linux prerequisites.
- Repository clone and Codex credential setup.
- `init`, `doctor`, and generated `.local` contents.
- Interactive SQLite account creation and automation-safe stdin setup.
- Optional TqSdk credentials and AkShare fallback.
- Start, login, status, and deployment acceptance.
- Account administration and session behavior.
- Upgrade, backup, restore, and migration.
- Troubleshooting and development verification.

**Step 3: Add the English section**

Mirror every Chinese topic in clear English. Reuse the same command values and
paths. Do not shorten the English installation or account sections.

**Step 4: Keep security-sensitive examples safe**

Use placeholders such as `<username>` and `<your-code-cli-api-key>`. Do not
include a real password, API key, reusable token, database content, or a copied
`.local/env`.

### Task 3: Verify documentation accuracy

**Files:**
- Verify: `README.md`
- Verify: `tests/deployment/test_readme.py`

**Step 1: Run the README contract**

Run:

```sh
pytest -q tests/deployment/test_readme.py
```

Expected: all README tests pass.

**Step 2: Verify referenced commands exist**

Run:

```sh
test -x ./bin/trading-agent-local
test -x ./trading-agent.sh
./bin/trading-agent-local --help
```

Expected: both scripts are executable and the local runner lists the supported
commands.

**Step 3: Run repository documentation-adjacent checks**

Run:

```sh
pytest -q tests/deployment
ruff check tests/deployment/test_readme.py
git diff --check
```

Expected: all checks pass.

**Step 4: Scan the README diff for secrets**

Confirm the diff contains no real password, API token, session token, SQLite
database, or `.local` artifact.

### Task 4: Commit and publish

**Files:**
- Add: `README.md`
- Add: `tests/deployment/test_readme.py`
- Add: `docs/plans/2026-07-30-bilingual-readme.md`

**Step 1: Commit the implementation**

```sh
git add README.md tests/deployment/test_readme.py docs/plans/2026-07-30-bilingual-readme.md
git commit -m "docs: add bilingual deployment readme"
```

**Step 2: Synchronize GitHub**

Use a normal non-force push when Git Smart HTTP is available. If the standard
transport is unavailable, verify the authenticated GitHub API state before
using the already established official Git Data API publication path.

**Step 3: Verify the remote**

Confirm:

- The private repository default branch is `main`.
- Remote `README.md` exists.
- Remote README blob SHA matches the local file.
- The language selector, Chinese section, and English section are present.
