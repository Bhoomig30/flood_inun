from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd


# ============================================================
# FLOODWATCH FUTURE PREDICTION
# ============================================================
#
# Uses the latest available row from forecast_dataset.csv.
#
# This is intentionally an offline/research inference script.
# The dashboard API can later call the same model logic.
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ML_DIR / "data"
FORECAST_DIR = DATA_DIR / "forecast"
MODEL_DIR = DATA_DIR / "models"

DATASET = FORECAST_DIR / "forecast_dataset.csv"
METADATA = MODEL_DIR / "flood_forecast_metadata.json"


def risk(probability):
    if probability >= 0.75:
        return "HIGH"
    if probability >= 0.50:
        return "MODERATE"
    return "LOW"


def main():
    if not DATASET.exists():
        raise FileNotFoundError(
            "Run build_forecast_dataset.py first."
        )

    if not METADATA.exists():
        raise FileNotFoundError(
            "Run train_flood_forecast.py first."
        )

    meta = json.loads(
        METADATA.read_text(encoding="utf-8")
    )

    df = pd.read_csv(
        DATASET,
        parse_dates=["timestamp"]
    ).sort_values("timestamp")

    # Latest feature timestamp only.
    row = df.iloc[-1]

    output = {
        "timestamp": str(row["timestamp"]),
        "location": {
            "latitude": float(row["scene_location_lat"]),
            "longitude": float(row["scene_location_lon"]),
        },
        "forecast": {},
        "warning": (
            "This is a model prediction from historical CWC data. "
            "It is not a live government warning."
        ),
    }

    excluded = {
        "timestamp",
        "rain_station",
        "river_station",
        "flood_next_6h",
        "flood_next_12h",
        "flood_next_24h",
    }

    feature_columns = meta["features"]
    x = pd.DataFrame(
        [[row[c] for c in feature_columns]],
        columns=feature_columns
    )

    for horizon in meta["horizons_hours"]:
        target = f"flood_next_{horizon}h"

        if meta["metrics"].get(target, {}).get("status") != "trained":
            output["forecast"][f"{horizon}h"] = {
                "status": "not_trained",
                "reason": meta["metrics"][target].get(
                    "status",
                    "unknown"
                ),
            }
            continue

        model = joblib.load(
            MODEL_DIR / f"flood_forecast_{horizon}h.pkl"
        )
        imputer = joblib.load(
            MODEL_DIR / f"flood_forecast_{horizon}h_imputer.pkl"
        )

        x2 = imputer.transform(x)
        probability = float(
            model.predict_proba(x2)[0, 1]
        )

        output["forecast"][f"{horizon}h"] = {
            "flood_probability": round(probability, 4),
            "risk": risk(probability),
        }

    print(
        json.dumps(
            output,
            indent=2
        )
    )


if __name__ == "__main__":
    main()
