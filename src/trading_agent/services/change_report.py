from typing import Any


def build_change_report(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    current_action = current["decision"]["action"]
    if previous is None:
        return {
            "summary": f"首次分析完成，当前动作：{current_action}。",
            "previous_action": None,
            "current_action": current_action,
            "changed_steps": [step["number"] for step in current["milestones"]],
            "new_evidence_hashes": [
                evidence["image_sha256"] for evidence in current.get("evidence_set", [])
            ],
        }
    previous_steps = {
        step["number"]: (step["status"], step["result"])
        for step in previous.get("milestones", [])
    }
    changed_steps = [
        step["number"]
        for step in current["milestones"]
        if previous_steps.get(step["number"]) != (step["status"], step["result"])
    ]
    previous_hashes = {
        evidence["image_sha256"] for evidence in previous.get("evidence_set", [])
    }
    new_hashes = [
        evidence["image_sha256"]
        for evidence in current.get("evidence_set", [])
        if evidence["image_sha256"] not in previous_hashes
    ]
    previous_action = previous["decision"]["action"]
    return {
        "summary": (
            f"动作从 {previous_action} 更新为 {current_action}；"
            f"变化步骤：{changed_steps or '无'}。"
        ),
        "previous_action": previous_action,
        "current_action": current_action,
        "changed_steps": changed_steps,
        "new_evidence_hashes": new_hashes,
    }
