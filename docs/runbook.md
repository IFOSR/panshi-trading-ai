# Trading Agent Runbook

1. Keep `TRADING_AGENT_ENABLE_ORDER_EXECUTION=false`.
2. Start dependencies with `docker compose up -d postgres redis minio temporal`.
3. Apply migrations before starting API and worker processes.
4. Verify `/docs`, case creation, eight milestones, and risk-veto behavior.
5. On provider failure, confirm Codex availability; Kimi is used only when
   `image_in` capability is verified.
6. Preserve event, evidence, decision, model, prompt, strategy, risk, and rule
   versions when raw-image retention expires.
