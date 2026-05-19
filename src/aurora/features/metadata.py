"""Feature set metadata for reproducible research workflows."""

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import uuid

import pandas as pd

from aurora.features.build_features import get_feature_columns


@dataclass(frozen=True)
class FeatureSetMetadata:
    """Metadata describing a generated feature set."""

    feature_set_id: str
    created_at: str
    symbols: list[str]
    source: str | None
    timeframe: str | None
    row_count: int
    feature_count: int
    features: list[str]
    config_hash: str


def make_config_hash(config: dict) -> str:
    """Create a deterministic hash for a feature configuration."""
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def create_feature_metadata(
    df: pd.DataFrame,
    feature_df: pd.DataFrame,
    config: dict,
    timeframe: str | None = None,
) -> FeatureSetMetadata:
    """Create metadata for a generated feature dataframe."""
    created_at = datetime.now(UTC).isoformat()
    config_hash = make_config_hash(config)
    symbols = sorted(str(symbol) for symbol in df["symbol"].dropna().unique())
    sources = sorted(str(source) for source in df["source"].dropna().unique()) if "source" in df else []
    features = get_feature_columns(feature_df)

    return FeatureSetMetadata(
        feature_set_id=f"features_{config_hash}_{uuid.uuid4().hex[:8]}",
        created_at=created_at,
        symbols=symbols,
        source=sources[0] if len(sources) == 1 else None,
        timeframe=timeframe,
        row_count=len(feature_df),
        feature_count=len(features),
        features=features,
        config_hash=config_hash,
    )
