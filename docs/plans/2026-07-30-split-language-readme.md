# Split-Language README Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the root README default to Chinese, move English documentation to a separate page, and remove backup, restore, and server-migration guidance.

**Architecture:** Keep `README.md` as the complete Chinese GitHub landing page and add `README.en.md` as the complete English page. Each page links directly to the other, while a pytest documentation contract protects navigation, retained deployment content, language separation, and removed operational sections.

**Tech Stack:** GitHub Markdown, Mermaid, pytest, POSIX shell commands.

---

### Task 1: Replace the single-page documentation contract

**Files:**
- Modify: `tests/deployment/test_readme.py`
- Test: `tests/deployment/test_readme.py`

**Step 1: Write the failing tests**

Require:

- `README.md` and `README.en.md`;
- Chinese as the root page and English as the linked page;
- reciprocal relative links;
- no same-page Chinese or English anchors;
- architecture, installation, account, market-data, and safety content in each
  language;
- no backup, restore, server-migration headings, or destructive restore
  commands.

**Step 2: Run the test to verify it fails**

Run:

```sh
pytest -q tests/deployment/test_readme.py
```

Expected: FAIL because `README.en.md` does not exist and the root README still
contains both languages and removed sections.

### Task 2: Create the two language-specific pages

**Files:**
- Rewrite: `README.md`
- Create: `README.en.md`

**Step 1: Rewrite the root page**

Make `README.md` the complete Chinese page. Put this navigation first:

```markdown
**中文** | [English](README.en.md)
```

Retain product positioning, trust architecture, local installation, account
configuration, market data, runtime commands, acceptance, troubleshooting, and
development verification.

**Step 2: Add the English page**

Create `README.en.md` with equivalent English content and this navigation:

```markdown
[中文](README.md) | **English**
```

**Step 3: Remove excluded operations**

Do not include SQLite backup, restore, server migration, `.local/env` backup,
`rm -rf`, or `before-restore` commands in either page.

**Step 4: Run the contract**

Run:

```sh
pytest -q tests/deployment/test_readme.py
```

Expected: PASS.

### Task 3: Verify and publish

**Files:**
- Verify: `README.md`
- Verify: `README.en.md`
- Verify: `tests/deployment/test_readme.py`

**Step 1: Run documentation and repository checks**

```sh
pytest -q tests/deployment
ruff check tests/deployment/test_readme.py
git diff --check
pytest -q
```

Expected: all checks pass.

**Step 2: Check secrets and navigation**

Confirm both pages contain only placeholders, use reciprocal relative links,
and do not contain the removed operational sections.

**Step 3: Commit**

```sh
git add README.md README.en.md tests/deployment/test_readme.py \
  docs/plans/2026-07-30-split-language-readme.md
git commit -m "docs: split readme by language"
```

**Step 4: Synchronize GitHub**

Publish the design and implementation commits to `main` without force. Verify
the remote file blobs and language links after publication.
