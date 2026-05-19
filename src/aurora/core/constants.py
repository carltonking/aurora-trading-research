"""Project-wide constants."""

PROJECT_NAME = "AURORA Trading Research"
PROJECT_ACRONYM = "Autonomous Universe-aware Research Optimization & Risk-managed Algorithm"
DEFAULT_MODE = "research"
SUPPORTED_MODES = {"research", "paper"}
UNSUPPORTED_V1_FEATURES = {
    "live_trading",
    "alpaca_live_trading",
    "alpaca_paper_trading",
    "lseg_workspace_adapter",
    "options_trading",
    "margin_trading",
    "crypto_trading",
}
