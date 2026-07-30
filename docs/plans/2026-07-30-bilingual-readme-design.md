# Bilingual README Design

Date: 2026-07-30
Status: Approved

## Goal

Create a root `README.md` that lets a reader understand the product, evaluate
its architecture, and deploy a working local instance without consulting other
documents.

The README must emphasize:

1. The logical architecture and trust boundaries.
2. A detailed, executable installation guide, including SQLite account setup.
3. Product capabilities and differentiators that make the project worth
   deploying.

## Language Navigation

The README is a single Markdown page with a language selector at the top:

```text
Language / 语言
[中文] [English]
```

Each link targets a stable anchor in the same document. The Chinese and English
sections are complete, independent documents. Each language section includes a
link back to the language selector.

GitHub Markdown anchors are used instead of scripted tabs so navigation works
without JavaScript and remains compatible with GitHub rendering.

## Information Architecture

Both language sections use the same order:

1. Product positioning and safety boundary.
2. Feature highlights.
3. Logical architecture diagram.
4. Analysis data flow and decision trust chain.
5. Deployment prerequisites.
6. Codex model credential configuration.
7. Repository initialization and dependency installation.
8. SQLite user creation and account administration.
9. Optional free China-futures data configuration.
10. Service startup, login, and deployment verification.
11. Daily operations, upgrade, backup, restore, and server migration.
12. Troubleshooting.
13. Development and test commands.

Commands are semantically identical across both language sections. Any future
change to a deployment command must update both sections in the same commit.

## Architecture Presentation

The README uses a Mermaid flowchart plus a short component table. The diagram
shows:

```text
Browser
  -> Next.js Web and server-side proxy
  -> FastAPI application
     -> SQLite users, sessions, cases, and analyses
     -> Original image storage
     -> Direct Codex multimodal extraction
     -> TqSdk/AkShare public market data
     -> Strategy registry and deterministic strategy plugin
     -> Independent risk engine
     -> Auditable conclusion and milestones
```

The architecture section explicitly states that:

- The model reads original screenshots directly; OpenCV and local OCR are not
  part of the production evidence path.
- The language model extracts and explains evidence but cannot independently
  decide the final trading action.
- The deterministic strategy plugin and risk engine own the final decision.
- Strategy plugins are versioned and decoupled from the conversation, data,
  authentication, and UI layers.
- The default local deployment does not require Docker, PostgreSQL, Redis,
  MinIO, Temporal, or a separate worker.

## Installation Contract

The primary installation path is the supported local lightweight runtime on
macOS or Linux:

```sh
git clone <repository>
cd panshi-trading-ai
export CODE_CLI_API_KEY=...
./bin/trading-agent-local init
./bin/trading-agent-local doctor
set -a
. .local/env
set +a
.local/venv/bin/panshi-user set-password <username>
./trading-agent.sh start
```

The README explains what each command changes and where persistent data lives.
It must not include a default plaintext password. Interactive password entry is
the recommended path; `--password-stdin` is documented only for automation.

The deployment guide also documents:

- `http://127.0.0.1:8989` as the user-facing URL.
- `http://127.0.0.1:8000/docs` as the API documentation URL.
- SQLite at `.local/data/trading-agent.db`.
- Original images at `.local/data/images`.
- Logs under `.local/logs`.
- Twelve-hour absolute browser sessions.
- Optional TqSdk credentials and automatic AkShare fallback.
- `TRADING_AGENT_ENABLE_ORDER_EXECUTION=false` as a required safety setting.

## Verification

Documentation verification covers:

- All referenced files and commands exist.
- The startup script exposes only `start`, `stop`, and `restart`.
- The local runtime exposes `init`, `doctor`, and `status`.
- README links and language anchors resolve.
- No real password, API key, session token, SQLite database, or `.local`
  runtime artifact is added to Git.
- Existing backend, type, build, and browser tests remain unaffected.
