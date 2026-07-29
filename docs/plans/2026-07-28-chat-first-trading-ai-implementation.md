# 磐石交易AI对话优先重构 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将现有截图分析控制台改造成桌面端对话式交易分析产品，并通过策略SDK和注册表将具体交易策略从会话、数据、风控和UI中解耦。

**Architecture:** 保留现有多模态证据、公开行情、风险和分析版本能力，在其上增加通用策略契约、策略注册表和会话消息投影。当前结构确认策略作为默认插件接入；前端只消费策略清单、动态里程碑和通用结论，不写死策略名称或固定步骤数量。

**Tech Stack:** Python 3.10、FastAPI、Pydantic、SQLAlchemy、Next.js 15、React 19、TypeScript、Playwright、pytest。

---

### Task 1: Strategy SDK and registry

**Files:**
- Create: `src/trading_agent/strategies/contracts.py`
- Create: `src/trading_agent/strategies/registry.py`
- Create: `src/trading_agent/strategies/structure_confirmation.py`
- Create: `src/trading_agent/strategies/__init__.py`
- Modify: `src/trading_agent/domain/milestone.py`
- Modify: `src/trading_agent/domain/decision.py`
- Test: `tests/strategies/test_registry.py`
- Test: `tests/strategies/test_contracts.py`

1. Write failing tests for manifest discovery, version selection, duplicate rejection, unknown strategy errors, dynamic milestone counts and default strategy metadata.
2. Run the focused tests and verify they fail before production files exist.
3. Implement `StrategyManifest`, `StrategyInputSnapshot`, `StrategyRun`, `StrategyPlugin` and `StrategyRegistry`.
4. Wrap the existing structure-confirmation evaluator as the default plugin.
5. Relax generic milestone and decision validation so the shared domain no longer requires exactly eight steps.
6. Run focused strategy contract tests and existing strategy tests.

### Task 2: Route analysis through the selected strategy

**Files:**
- Modify: `src/trading_agent/workflows/analysis.py`
- Modify: `src/trading_agent/services/analysis.py`
- Modify: `src/trading_agent/workflows/activities.py`
- Modify: `src/trading_agent/security/audit.py`
- Modify: `src/trading_agent/db/repositories.py`
- Test: `tests/workflows/test_analysis_workflow.py`
- Test: `tests/api/test_case_flow.py`

1. Write failing tests proving the workflow resolves a strategy through the registry and stores strategy ID, display name, version and process label in each analysis.
2. Add a fake strategy with a non-eight-step result and verify the workflow/UI payload accepts it.
3. Store the selected strategy on case creation and pin each analysis to an exact version.
4. Keep risk evaluation and final action outside the plugin.
5. Ensure existing cases without strategy metadata automatically resolve to the default strategy.
6. Run workflow, API, risk and rendering regression tests.

### Task 3: Strategy and conversation APIs

**Files:**
- Modify: `src/trading_agent/api/app.py`
- Modify: `src/trading_agent/db/repositories.py`
- Create: `src/trading_agent/conversation/models.py`
- Create: `src/trading_agent/conversation/service.py`
- Create: `src/trading_agent/providers/conversation.py`
- Modify: `src/trading_agent/providers/base.py`
- Test: `tests/api/test_conversation_flow.py`
- Test: `tests/providers/test_conversation_provider.py`
- Test: `tests/db/test_repositories.py`

1. Write failing tests for listing strategies, listing recent conversations, selecting a strategy and retrieving a conversation timeline.
2. Write failing tests for an explanation follow-up that is bound to the latest immutable analysis and cannot change its final action.
3. Add conversation events for user messages, assistant explanations and strategy changes.
4. Implement a Codex text provider with a strict response schema and deterministic fallback.
5. Add `GET /v1/strategies`, `GET /v1/cases`, `GET /v1/cases/{id}/conversation`, `POST /v1/cases/{id}/messages` and `POST /v1/cases/{id}/strategy`.
6. Preserve idempotency and API-token enforcement for all mutating commands.
7. Run focused API, provider and repository tests.

### Task 4: Next.js proxy and view models

**Files:**
- Modify: `web/app/api/analysis/route.ts`
- Create: `web/app/api/strategies/route.ts`
- Create: `web/app/api/cases/route.ts`
- Create: `web/app/api/cases/[caseId]/messages/route.ts`
- Create: `web/app/api/cases/[caseId]/strategy/route.ts`
- Modify: `web/lib/api.ts`
- Modify: `web/tests/api-server.mjs`
- Test: `web/tests/strategy-console.spec.ts`

1. Add failing proxy tests for safe local strategy and message requests.
2. Add strategy ID and version to analysis submission.
3. Map strategy manifests, analysis metadata and conversation messages into frontend-safe types.
4. Remove fixed eight-step progress calculations and derive progress from returned milestones.
5. Update the mock API server with strategy, case-list and message fixtures.
6. Run TypeScript and focused proxy tests.

### Task 5: Desktop Chat-first workspace

**Files:**
- Create: `web/components/trading-chat.tsx`
- Create: `web/components/conversation-sidebar.tsx`
- Create: `web/components/chat-composer.tsx`
- Create: `web/components/strategy-selector.tsx`
- Create: `web/components/strategy-audit-drawer.tsx`
- Modify: `web/components/analysis-input.tsx`
- Modify: `web/components/clarification-panel.tsx`
- Modify: `web/components/decision-summary.tsx`
- Modify: `web/components/strategy-milestone-rail.tsx`
- Modify: `web/app/page.tsx`
- Modify: `web/app/cases/[caseId]/page.tsx`
- Modify: `web/app/globals.css`
- Test: `web/tests/strategy-console.spec.ts`

1. Write failing E2E tests for the desktop conversation shell, persistent composer, attachment preview, default strategy selector, compact conclusion card, inline clarification and follow-up response.
2. Replace the multi-section home form with a ChatGPT-style initial conversation composer while keeping existing upload and analysis commands.
3. Render the case page as conversation history with the final conclusion inside an assistant message.
4. Integrate clarification questions into the same composer instead of a separate page section.
5. Add an on-demand strategy audit drawer that dynamically renders any milestone count.
6. Keep evidence, change report and full audit detail accessible from the drawer.
7. Remove mobile from Playwright projects and current acceptance scope.
8. Run focused desktop Playwright tests and inspect a real screenshot.

### Task 6: Full verification and real case

**Files:**
- Modify only when failures expose defects.

1. Run full pytest.
2. Run Ruff and Mypy.
3. Run TypeScript and production Next.js build.
4. Run full desktop Playwright.
5. Restart local services on web port 8989.
6. Open the existing CF2609 case and verify conversation, strategy selection, conclusion, follow-up input and audit drawer.
7. Submit a real explanation follow-up and verify the response remains aligned with the immutable strategy result.
8. Run `git diff --check` and report residual risks.
