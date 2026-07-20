import logging
from collections.abc import Mapping


logger = logging.getLogger("trading_agent")


def record_analysis_metric(name: str, attributes: Mapping[str, object]) -> None:
    logger.info("analysis_metric", extra={"metric_name": name, "attributes": dict(attributes)})
