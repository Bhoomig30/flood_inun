from pathlib import Path
import json

import joblib
import pandas as pd


# ============================================================
# FLOODWATCH FUTURE FLOOD FORECAST
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ML_DIR / "data"

FORECAST_DIR = DATA_DIR / "forecast"
MODEL_DIR = DATA_DIR / "models"

DATASET = FORECAST_DIR / "forecast_dataset.csv"
METADATA = MODEL_DIR / "flood_forecast_metadata.json"


# ============================================================
# RISK CLASSIFICATION
# ============================================================

def risk(probability):

    if probability >= 0.75:
        return "HIGH"

    if probability >= 0.50:
        return "MODERATE"

    return "LOW"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 80)
    print("FLOODWATCH FUTURE FLOOD FORECAST")
    print("=" * 80)

    # --------------------------------------------------------
    # CHECK FILES
    # --------------------------------------------------------

    if not DATASET.exists():

        raise FileNotFoundError(
            f"Forecast dataset not found:\n{DATASET}"
        )

    if not METADATA.exists():

        raise FileNotFoundError(
            f"Forecast model metadata not found:\n{METADATA}"
        )

    print("\nDataset:")
    print(DATASET)

    print("\nMetadata:")
    print(METADATA)

    # --------------------------------------------------------
    # LOAD METADATA
    # --------------------------------------------------------

    meta = json.loads(
        METADATA.read_text(
            encoding="utf-8"
        )
    )

    features = meta["features"]

    horizons = meta["horizons_hours"]

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    print("\nLoading forecast dataset...")

    df = pd.read_csv(
        DATASET,
        parse_dates=["timestamp"]
    )

    df = df.sort_values(
        "timestamp"
    ).reset_index(
        drop=True
    )

    print(
        "Rows:",
        len(df)
    )

    print(
        "Latest timestamp:",
        df["timestamp"].iloc[-1]
    )

    # --------------------------------------------------------
    # USE LATEST OBSERVATION
    # --------------------------------------------------------

    row = df.iloc[-1]

    # --------------------------------------------------------
    # BUILD FEATURE VECTOR
    # --------------------------------------------------------

    x = pd.DataFrame(
        [[
            pd.to_numeric(
                row[column],
                errors="coerce"
            )
            for column in features
        ]],
        columns=features
    )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    output = {

        "status": "success",

        "timestamp": str(
            row["timestamp"]
        ),

        # "location": {

        #     "latitude": float(
        #         row["scene_location_lat"]
        #     ),

        #     "longitude": float(
        #         row["scene_location_lon"]
        #     ),
        # },
        "location": {
            "latitude": 20.5,
            "longitude": 85.95,
        },

        "forecast": {},

        "warning": (
            "This is an AI/ML prediction based on "
            "historical CWC observations. It is not "
            "a live government flood warning."
        ),
    }

    # --------------------------------------------------------
    # PREDICT EACH HORIZON
    # --------------------------------------------------------

    for horizon in horizons:

        print("\n" + "-" * 80)

        print(
            f"Predicting {horizon}-hour flood risk..."
        )

        model_path = (
            MODEL_DIR
            / f"flood_forecast_{horizon}h.pkl"
        )

        imputer_path = (
            MODEL_DIR
            / f"flood_forecast_{horizon}h_imputer.pkl"
        )

        # ----------------------------------------------------
        # CHECK MODEL
        # ----------------------------------------------------

        if not model_path.exists():

            output["forecast"][
                f"{horizon}h"
            ] = {

                "status": "not_available",

                "reason": (
                    f"Model not found: "
                    f"{model_path.name}"
                ),
            }

            continue

        if not imputer_path.exists():

            output["forecast"][
                f"{horizon}h"
            ] = {

                "status": "not_available",

                "reason": (
                    f"Imputer not found: "
                    f"{imputer_path.name}"
                ),
            }

            continue

        # ----------------------------------------------------
        # LOAD MODEL
        # ----------------------------------------------------

        model = joblib.load(
            model_path
        )

        imputer = joblib.load(
            imputer_path
        )

        # ----------------------------------------------------
        # IMPUTE FEATURES
        # ----------------------------------------------------

        x_imputed = imputer.transform(
            x
        )

        # ----------------------------------------------------
        # PREDICT PROBABILITY
        # ----------------------------------------------------

        probability = float(
            model.predict_proba(
                x_imputed
            )[0, 1]
        )

        risk_level = risk(
            probability
        )

        print(
            f"Probability: "
            f"{probability:.4f}"
        )

        print(
            f"Risk: {risk_level}"
        )

        # ----------------------------------------------------
        # SAVE RESULT
        # ----------------------------------------------------

        output["forecast"][
            f"{horizon}h"
        ] = {

            "status": "predicted",

            "horizon_hours": horizon,

            "flood_probability": round(
                probability,
                4
            ),

            "flood_probability_percent": round(
                probability * 100,
                2
            ),

            "risk": risk_level,
        }

    # --------------------------------------------------------
    # PRINT JSON
    # --------------------------------------------------------

    print("\n" + "=" * 80)
    print("FORECAST RESULT")
    print("=" * 80)

    print(
        json.dumps(
            output,
            indent=2
        )
    )

    # --------------------------------------------------------
    # SAVE RESULT
    # --------------------------------------------------------

    output_file = (
        FORECAST_DIR
        / "latest_forecast.json"
    )

    output_file.write_text(
        json.dumps(
            output,
            indent=2
        ),
        encoding="utf-8"
    )

    print("\n" + "=" * 80)

    print(
        "Forecast saved:"
    )

    print(
        output_file
    )

    print("=" * 80)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()