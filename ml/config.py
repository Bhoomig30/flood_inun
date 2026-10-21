"""Single source of truth for paths and dataset location (no hardcoded user paths)."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ML_DIR = PROJECT_ROOT / "ml"
DATA_DIR = ML_DIR / "data"
DASHBOARD_DIR = PROJECT_ROOT / "naraj_dashboard"

HF_REPO_ID = "bhoomig0630/flood-inundation-upload"
HF_REPO_TYPE = "dataset"
MANIFEST_FILE = ML_DIR / "data_manifest.json"