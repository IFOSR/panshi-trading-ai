from trading_agent.workflows.analysis import AnalysisWorkflow


def build_worker() -> AnalysisWorkflow:
    return AnalysisWorkflow()
