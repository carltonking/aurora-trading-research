"""Local filesystem model registry."""

from dataclasses import asdict
import json
from pathlib import Path
import pickle

from aurora.models.exceptions import ModelRegistryError
from aurora.models.train import TrainingResult


def get_model_registry_dir(base_dir: str | Path = "data/models") -> Path:
    """Return the local model registry directory, creating it if needed."""
    path = Path(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_model_artifact(
    model: object,
    result: TrainingResult,
    base_dir: str | Path = "data/models",
) -> Path:
    """Save a trained model and its metadata to the local registry."""
    registry_dir = get_model_registry_dir(base_dir)
    model_dir = registry_dir / result.model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "model.pkl"
    metadata_path = model_dir / "metadata.json"
    result.model_path = str(model_dir)

    with model_path.open("wb") as file:
        pickle.dump(model, file)

    with metadata_path.open("w", encoding="utf-8") as file:
        json.dump(asdict(result), file, indent=2, sort_keys=True)

    return model_dir


def load_model_artifact(
    model_id: str,
    base_dir: str | Path = "data/models",
) -> tuple[object, dict]:
    """Load a model and metadata from the local registry."""
    model_dir = Path(base_dir) / model_id
    model_path = model_dir / "model.pkl"
    metadata_path = model_dir / "metadata.json"
    if not model_path.exists() or not metadata_path.exists():
        raise ModelRegistryError(f"Model artifact not found: {model_id}")

    with model_path.open("rb") as file:
        model = pickle.load(file)

    with metadata_path.open("r", encoding="utf-8") as file:
        metadata = json.load(file)

    return model, metadata


def list_model_artifacts(base_dir: str | Path = "data/models") -> list[dict]:
    """List saved model metadata sorted by newest training time first."""
    registry_dir = Path(base_dir)
    if not registry_dir.exists():
        return []

    metadata_items = []
    for metadata_path in registry_dir.glob("*/metadata.json"):
        try:
            with metadata_path.open("r", encoding="utf-8") as file:
                metadata_items.append(json.load(file))
        except json.JSONDecodeError as exc:
            raise ModelRegistryError(f"Invalid metadata file: {metadata_path}") from exc

    return sorted(metadata_items, key=lambda item: item.get("trained_at", ""), reverse=True)


class ModelRegistry:
    """Compatibility wrapper for the local model registry."""

    def __init__(self, base_dir: str | Path = "data/models") -> None:
        self.base_dir = base_dir

    def list_models(self) -> list[str]:
        """Return saved model identifiers."""
        return [metadata["model_id"] for metadata in list_model_artifacts(self.base_dir)]
