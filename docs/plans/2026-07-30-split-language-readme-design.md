# Split-Language README Design

## Goal

Present the repository documentation as two concise language-specific pages
instead of one long bilingual page.

## Page Structure

- `README.md` is the default Chinese page rendered by GitHub.
- `README.en.md` is the complete English page.
- Both pages show `[中文]` and `[English]` links at the top.
- The active language is plain bold text; the other language is a link.

The root page defaults to Chinese as requested. There is no separate language
selector landing page and no same-page anchor navigation.

## Content Scope

Both pages retain the same product and deployment scope:

- product positioning and safety boundary;
- multimodal evidence and deterministic strategy trust chain;
- logical Mermaid architecture;
- strategy registry and independent risk engine;
- local lightweight installation;
- Codex and free market-data configuration;
- SQLite login account creation and administration;
- start, stop, restart, status, acceptance, and troubleshooting;
- development and test commands.

The following operational sections are removed from both languages:

- SQLite backup;
- restore procedures;
- server migration.

The README does not include destructive restore commands or `.local/env`
backup guidance.

## Navigation

Chinese page:

```markdown
**中文** | [English](README.en.md)
```

English page:

```markdown
[中文](README.md) | **English**
```

Relative links keep navigation working on GitHub and in local Markdown
renderers.

## Verification

The documentation contract will verify:

- `README.md` exists and contains Chinese content only;
- `README.en.md` exists and contains English content only;
- both pages link to each other;
- same-page language anchors no longer exist;
- architecture, installation, account, market-data, and safety details remain
  complete in each language;
- backup, restore, migration, and destructive restore commands are absent.
