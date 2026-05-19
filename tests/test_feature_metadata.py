from aurora.features.build_features import DEFAULT_FEATURE_CONFIG, build_features, get_feature_columns
from aurora.features.metadata import create_feature_metadata, make_config_hash
from tests.test_build_features import _sample_ohlcv


def test_make_config_hash_is_deterministic() -> None:
    first = make_config_hash({"b": [2, 1], "a": {"enabled": True}})
    second = make_config_hash({"a": {"enabled": True}, "b": [2, 1]})

    assert first == second


def test_create_feature_metadata_returns_expected_fields() -> None:
    df = _sample_ohlcv(["MSFT", "AAPL"], periods=30)
    feature_df = build_features(df)

    metadata = create_feature_metadata(
        df,
        feature_df,
        DEFAULT_FEATURE_CONFIG,
        timeframe="1d",
    )

    assert metadata.symbols == ["AAPL", "MSFT"]
    assert metadata.source == "test"
    assert metadata.timeframe == "1d"
    assert metadata.row_count == len(feature_df)
    assert metadata.feature_count == len(get_feature_columns(feature_df))
    assert metadata.config_hash == make_config_hash(DEFAULT_FEATURE_CONFIG)
