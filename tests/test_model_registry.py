from pathlib import Path

import pytest

from aurora.models.exceptions import ModelRegistryError
from aurora.models.registry import list_model_artifacts, load_model_artifact, save_model_artifact
from aurora.models.train import TrainingResult


def _training_result(model_id: str = "model_test") -> TrainingResult:
    return TrainingResult(
        model_id=model_id,
        model_type="random_forest",
        trained_at="2026-01-01T00:00:00+00:00",
        row_count=120,
        feature_count=2,
        features=["return_1d", "ma_5"],
        metrics={
            "accuracy": 0.5,
            "precision": 0.4,
            "recall": 0.3,
            "f1": 0.2,
            "train_rows": 90,
            "test_rows": 30,
        },
        label_config={"horizon": 5},
    )


def test_save_model_artifact_creates_files(tmp_path: Path) -> None:
    model_dir = save_model_artifact({"model": "dummy"}, _training_result(), base_dir=tmp_path)

    assert (model_dir / "model.pkl").exists()
    assert (model_dir / "metadata.json").exists()


def test_load_model_artifact_returns_model_and_metadata(tmp_path: Path) -> None:
    save_model_artifact({"model": "dummy"}, _training_result(), base_dir=tmp_path)

    model, metadata = load_model_artifact("model_test", base_dir=tmp_path)

    assert model == {"model": "dummy"}
    assert metadata["model_id"] == "model_test"
    assert metadata["model_path"] == str(tmp_path / "model_test")


def test_list_model_artifacts_returns_saved_metadata(tmp_path: Path) -> None:
    save_model_artifact({"model": "one"}, _training_result("model_one"), base_dir=tmp_path)
    save_model_artifact(
        {"model": "two"},
        TrainingResult(
            **{
                **_training_result("model_two").__dict__,
                "trained_at": "2026-01-02T00:00:00+00:00",
            }
        ),
        base_dir=tmp_path,
    )

    metadata = list_model_artifacts(base_dir=tmp_path)

    assert [item["model_id"] for item in metadata] == ["model_two", "model_one"]


def test_missing_model_raises_model_registry_error(tmp_path: Path) -> None:
    with pytest.raises(ModelRegistryError):
        load_model_artifact("missing", base_dir=tmp_path)
