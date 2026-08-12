[中文](README.md) | **English**

# Panshi Trading AI

Multimodal, auditable strategy analysis for China's futures market.

## Product positioning

Panshi Trading AI is a desktop analysis and decision-support system. In a
continuous conversation, a user can submit a question and complete market
screenshots. The system performs:

- direct DeepSeek multimodal analysis of the original image;
- public market-data enrichment through TqSdk and AkShare;
- data consistency and validity checks;
- versioned deterministic strategy evaluation;
- independent risk validation;
- a final action aligned with every strategy milestone;
- auditable disclosure of evidence, milestones, and blockers;
- follow-up explanation of conclusions, rules, evidence, and risk controls.

The product does not ask a language model to guess market direction from a
chart. It combines multimodal evidence, public data, deterministic strategy
logic, independent risk controls, and an inspectable user experience.

> **Safety boundary:** this release provides analysis and decision support only.
> Keep `TRADING_AGENT_ENABLE_ORDER_EXECUTION=false`. It does not connect to a live order gateway
> and does not replace licensed advice, exchange rules, or the operator's own risk controls.

## Highlights

### Direct original-image understanding

The runtime sends the complete user screenshot directly to the DeepSeek
multimodal model. OpenCV, image slicing, local OCR, and coordinate
reconstruction are not used as substitutes in the production evidence path.
Contract, timeframe, candles, indicators, and surrounding UI context remain
available to the model.

### Automatic public-data enrichment

The system derives prices, volume, open interest, trading dates, and indicator
inputs from the screenshot, TqSdk, AkShare, and exchange daily data. It asks
the user only for private facts such as actual position details, account risk
limits, or a genuine conflict about the screenshot's target.

### Strategy and risk control the final action

The language model extracts, summarizes, and explains evidence, but **cannot independently decide**
the final action. A deterministic strategy plugin emits the candidate action,
and the independent Risk Engine can veto any signal.

### Every core step is auditable

Each analysis records the strategy ID and version, milestone inputs, rule
comparisons, screenshot evidence, public-market evidence, field provenance,
model version, confidence, blockers, and next trigger conditions. The product
shows verifiable execution records rather than hidden model reasoning.

### Strategies are decoupled from the application

The Web, conversation, data, authentication, and risk layers do not hard-code
one strategy. A **Strategy Registry** loads and pins versioned plugins. The
default plugin is `Structure Confirmation Strategy v1.0.0`; future strategies
can be installed, upgraded, disabled, and rolled back independently.

## Logical architecture

```mermaid
flowchart TD
    U[User browser<br/>Question + original screenshots + private position facts]
    W[Next.js Web :8989<br/>Login, conversation, attachments, strategy selection]
    A[FastAPI :8005<br/>Conversation, evidence, and analysis orchestration]

    DB[(SQLite<br/>Users, sessions, cases, analysis versions)]
    IMG[(Original image storage<br/>.local/data/images)]
    V[DeepSeek multimodal model<br/>Direct original-image reading]
    M[Free market data<br/>TqSdk primary / AkShare fallback]
    E[Evidence merge and validity<br/>Sources, conflicts, confidence, freshness]
    R[Strategy Registry]
    S[Versioned strategy plugin<br/>Deterministic milestone evaluation]
    K[Independent Risk Engine]
    O[Auditable conclusion<br/>Action, evidence, blockers, next conditions]

    U --> W
    W --> A
    A --> DB
    A --> IMG
    A --> V
    A --> M
    V --> E
    M --> E
    E --> R
    R --> S
    S --> K
    K --> O
    O --> DB
    O --> W
```

### Component responsibilities

| Component | Responsibility |
| --- | --- |
| Next.js Web | SQLite login, continuous conversation, screenshot attachments, strategy selection, and history |
| FastAPI | API authentication, original-image storage, case state, orchestration, and session management |
| SQLite | Password hashes, session digests, case events, and analysis versions |
| DeepSeek | Reads original images and emits structured observations, visible text, confidence, and uncertainty |
| TqSdk / AkShare | China-futures public data; TqSdk is optional and AkShare is the automatic fallback |
| Evidence layer | Merges screenshots and structured data and detects conflicts, missing fields, close status, and quality |
| Strategy Registry | Discovers, selects, and pins strategy plugin versions |
| Strategy plugin | Produces milestones and candidate actions from explicit rules |
| Risk Engine | Checks risk budget, stop distance, and correlated exposure and can veto an action |
| Conversation layer | Renders immutable strategy output and answers follow-up questions |

### Screenshot-to-decision flow

```text
User question and complete original screenshots
  -> direct DeepSeek multimodal extraction
  -> TqSdk / AkShare public-market enrichment
  -> evidence merge, provenance, and data-validity evaluation
  -> select and pin strategy ID and version
  -> execute deterministic strategy milestones
  -> validate or veto through the independent Risk Engine
  -> generate a final action aligned with every milestone
  -> store a new analysis version and continue the conversation
```

## Default deployment mode

The recommended path is the Docker-free local lightweight runtime:

```text
Browser -> Next.js :8989 -> FastAPI :8005
                              |-> SQLite
                              |-> original-image directory
                              |-> DeepSeek API
                              `-> inline strategy analysis
```

Only Next.js and FastAPI run as long-lived processes. PostgreSQL, Redis, MinIO,
Temporal, a separate worker, and an OTel Collector are not required.

## Installation

### 1. Requirements

- macOS or Linux;
- Python 3.10 or newer;
- Node.js 20 or newer;
- npm and Git;
- an available DeepSeek API Key;
- a model-provider API key available through an environment variable;
- free local ports `8005` and `8989`.

Check the required commands:

```sh
python3 --version
node --version
npm --version
git --version
```

### 2. Clone the repository

The public repository can be cloned without signing in:

```sh
git clone https://github.com/IFOSR/panshi-trading-ai.git
cd panshi-trading-ai
```

GitHub CLI is also supported:

```sh
gh repo clone IFOSR/panshi-trading-ai
cd panshi-trading-ai
```

### 3. Configure DeepSeek credentials

DeepSeek is the primary multimodal provider, with Kimi as the fallback. Initialization reads
`DEEPSEEK_API_KEY` from the current shell:

```sh
export DEEPSEEK_API_KEY=<your-deepseek-api-key>
```

Never place a real key in the README, Git, `.env.example`, or a startup script.
Initialization writes the credential to the private mode-`0600` `.local/env`.

For another compatible provider, update the initialized environment:

```sh
TRADING_AGENT_DEEPSEEK_MODEL=deepseek-chat
TRADING_AGENT_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
TRADING_AGENT_DEEPSEEK_ENV_KEY=DEEPSEEK_API_KEY
DEEPSEEK_API_KEY=<your-deepseek-api-key>
```

### 4. Initialize

Run from the repository root:

```sh
./bin/trading-agent-local init
./bin/trading-agent-local doctor
```

`init` creates the Python environment, installs dependencies, builds the Web
application, generates local settings, initializes SQLite, and checks DeepSeek
and market-data dependencies. Important local paths are:

```text
.local/env                         private runtime configuration and secrets
.local/venv/                       Python virtual environment
.local/data/trading-agent.db       SQLite database
.local/data/images/                original user screenshots
.local/logs/api.log                FastAPI log
.local/logs/web.log                Next.js log
.local/run/                        PIDs and process metadata
```

`.local` is ignored by Git. Never commit its contents.

### 5. Create a login account

Accounts and password hashes live in SQLite rather than source code or
environment variables. Load the database URL:

```sh
set -a
. .local/env
set +a
```

Create an account or change its password interactively:

```sh
.local/venv/bin/panshi-user set-password <username>
```

The command prompts twice without echoing the password. Automation can provide
one password through standard input:

```sh
printf '%s\n' '<password>' \
  | .local/venv/bin/panshi-user set-password <username> --password-stdin
```

Do not put a real password in a command-line argument, `.local/env`, a script,
or Git.

### 6. Configure free China-futures data

Local mode defaults to:

```sh
TRADING_AGENT_MARKET_DATA_PROVIDER=free
```

- TqSdk is the primary source when a free Kuaiqi account is configured;
- the runtime performs an automatic **AkShare fallback** when TqSdk is absent
  or unavailable;
- closed daily bars can be checked against exchange daily reports;
- provider provenance and quality warnings appear in the data-validity step.

To enable TqSdk, edit `.local/env`:

```sh
TRADING_AGENT_TQSDK_USERNAME=<your-free-tq-account>
TRADING_AGENT_TQSDK_PASSWORD=<your-free-tq-password>
```

The system still runs through AkShare when these fields are empty. Market-data
credentials remain on the backend and are never sent to the browser.

### 7. Confirm the safety setting

Keep this value in `.local/env`:

```sh
TRADING_AGENT_ENABLE_ORDER_EXECUTION=false
```

Do not change it to `true` in this release.

### 8. Start the services

```sh
./trading-agent.sh start
```

Open:

- Web: `http://127.0.0.1:8989`
- API documentation: `http://127.0.0.1:8005/docs`

Check runtime status:

```sh
./bin/trading-agent-local status
```

## User workflow

1. Sign in with a SQLite account.
2. Select a strategy and enter an analysis question.
3. Attach one or two complete screenshots containing the contract, timeframe,
   and full chart context.
4. The system sends the originals to DeepSeek and enriches public market data.
5. The conversation displays data validity, strategy milestones, risk
   constraints, and the final action.
6. Ask follow-up questions about the conclusion, rules, evidence, or risk.
7. Only genuine ambiguity that remains after image and public-data analysis
   enters a clarification dialogue.
8. New evidence creates a new analysis version without mutating the original.

## Daily operations

### Start, stop, restart, and status

```sh
./trading-agent.sh start
./trading-agent.sh stop
./trading-agent.sh restart
./bin/trading-agent-local status
./bin/trading-agent-local doctor
```

### Account administration

```sh
set -a
. .local/env
set +a

.local/venv/bin/panshi-user set-password <username>
.local/venv/bin/panshi-user disable <username>
.local/venv/bin/panshi-user enable <username>
```

- `set-password` creates an account or rotates its password and revokes all
  current sessions for that user;
- `disable` deactivates the account and revokes all sessions;
- `enable` reactivates the account but does not restore old sessions;
- browser sessions have a **12-hour** absolute lifetime;
- SQLite stores salted scrypt password hashes and session-token digests.

### Update the application

```sh
./trading-agent.sh stop
git pull --ff-only
export DEEPSEEK_API_KEY=<your-deepseek-api-key>
./bin/trading-agent-local init
./bin/trading-agent-local doctor
./trading-agent.sh start
```

## Troubleshooting

### DeepSeek is unavailable

```sh
echo $DEEPSEEK_API_KEY
./bin/trading-agent-local doctor
```

Confirm that the current shell contains the provider credential and inspect
the model-provider fields in `.local/env`.

### The Web UI is unavailable

```sh
./bin/trading-agent-local status
tail -n 100 .local/logs/web.log
```

Confirm that port `8989` is free and the production Web build exists.

### The API fails to start

```sh
tail -n 100 .local/logs/api.log
./bin/trading-agent-local doctor
```

Confirm that port `8005` is free, the SQLite URL is absolute, and `.local/env`
has the correct permissions.

### Login returns to the login page

Check API status, account state, and whether the session exceeded 12 hours.
Rotate the password with `panshi-user set-password` when necessary.

### TqSdk is unavailable

TqSdk is optional. Check its credentials and restart; without it, the system
should report an **AkShare fallback**. If every public source is unavailable,
the strategy blocks steps that require precise market data instead of asking
the user to re-enter publicly obtainable facts.

## Development and tests

Backend:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
ruff check .
mypy
```

Frontend:

```sh
cd web
npm ci
npm run lint
npm run build
npm run test:e2e
```

See `docs/runbook.md` for the full runtime reference and
`docs/evaluation.md` for multimodal evaluation.
