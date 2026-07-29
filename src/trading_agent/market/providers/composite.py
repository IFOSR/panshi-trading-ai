import re
from collections.abc import Mapping, Sequence

from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.providers.base import MarketDataProvider, MarketDataRequest
from trading_agent.market.providers.validation import SnapshotValidator
from trading_agent.market.resolver import MarketDataFailure, MarketDataSnapshot


ROLE_TIMEFRAMES = {
    "STATE_DAILY": "1d",
    "EXECUTION_60M": "60m",
}
TIMEFRAME_ALIASES = {
    "D1": "1d",
    "1D": "1d",
    "1d": "1d",
    "H1": "60m",
    "1h": "60m",
    "60m": "60m",
}


def _quality_issue(provider_name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", provider_name.upper()).strip("_")
    return f"{normalized}_UNAVAILABLE"


class FreeMarketDataResolver:
    def __init__(
        self,
        providers: Sequence[MarketDataProvider],
        *,
        validators: Sequence[SnapshotValidator] = (),
    ) -> None:
        self.providers = list(providers)
        self.validators = list(validators)

    def resolve(
        self,
        case_state: Mapping[str, object],
        evidence: ScreenshotEvidence,
    ) -> MarketDataSnapshot | MarketDataFailure | None:
        raw_contract = case_state.get("contract") or evidence.contract
        if not raw_contract:
            return None
        raw_timeframe = evidence.timeframe or ROLE_TIMEFRAMES.get(evidence.image_role)
        timeframe = TIMEFRAME_ALIASES.get(str(raw_timeframe), str(raw_timeframe))
        if not timeframe:
            return None
        request = MarketDataRequest(
            contract=str(raw_contract).strip(),
            timeframe=timeframe,
            image_role=evidence.image_role,
            evidence_cutoff_time=evidence.cutoff_time,
        )
        quality_issues: list[str] = []
        for index, provider in enumerate(self.providers):
            snapshot = None
            max_attempts = 2 if index == len(self.providers) - 1 else 1
            for _ in range(max_attempts):
                try:
                    snapshot = provider.fetch(request)
                except Exception:
                    snapshot = None
                if snapshot is not None:
                    break
            if snapshot is None:
                quality_issues.append(_quality_issue(provider.name))
                continue
            resolved = snapshot.model_copy(
                update={
                    "quality_issues": list(
                        dict.fromkeys([*quality_issues, *snapshot.quality_issues])
                    )
                }
            )
            for validator in self.validators:
                try:
                    resolved = validator.validate(resolved)
                except Exception:
                    resolved = resolved.model_copy(
                        update={
                            "quality_issues": list(
                                dict.fromkeys(
                                    [
                                        *resolved.quality_issues,
                                        "MARKET_DATA_VALIDATION_UNAVAILABLE",
                                    ]
                                )
                            )
                        }
                    )
            return resolved
        return MarketDataFailure(
            contract=request.contract,
            timeframe=request.timeframe,
            quality_issues=quality_issues,
        )
