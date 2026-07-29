import json
from pathlib import Path


DATASETS = Path("evals/datasets")


def test_dataset_schemas_describe_real_evaluator_inputs() -> None:
    vision_schema = json.loads((DATASETS / "schema.json").read_text(encoding="utf-8"))
    strategy_schema = json.loads(
        (DATASETS / "strategy_schema.json").read_text(encoding="utf-8")
    )

    assert {"record_id", "dataset_version", "image_path", "split", "labels"} <= set(
        vision_schema["required"]
    )
    assert {"prediction", "latency_seconds", "cost"}.isdisjoint(
        vision_schema["properties"]
    )
    assert vision_schema["additionalProperties"] is False
    assert {"bars", "walk_forward", "strategy_cases", "costs"} <= set(
        strategy_schema["required"]
    )
    assert "orders" not in strategy_schema["properties"]
