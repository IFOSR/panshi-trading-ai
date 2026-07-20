from trading_agent.providers.base import ProviderUnavailable, VisionProvider, VisionRequest


class FallbackVisionProvider:
    def __init__(self, primary: VisionProvider, fallback: VisionProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def analyze(self, request: VisionRequest):
        try:
            return self.primary.analyze(request)
        except ProviderUnavailable:
            return self.fallback.analyze(request)

