from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)


# ============================================================
# FLOODWATCH FUTURE FORECAST MODEL TRAINING
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ML_DIR / "data"

FORECAST_DIR = DATA_DIR / "forecast"
MODEL_DIR = DATA_DIR / "models"

DATASET = (
    FORECAST_DIR
    / "forecast_dataset.csv"
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)

HORIZONS = [6, 12, 24]

RANDOM_STATE = 42


# ============================================================
# LOAD DATASET
# ============================================================

print("=" * 80)
print("FLOODWATCH FUTURE FLOOD FORECAST MODEL TRAINING")
print("=" * 80)

if not DATASET.exists():

    raise FileNotFoundError(
        f"Dataset not found:\n{DATASET}"
    )


print("\nLoading dataset...")

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
    f"{len(df):,}"
)

print(
    "Columns:",
    len(df.columns)
)

print(
    "Time range:",
    df["timestamp"].min(),
    "->",
    df["timestamp"].max()
)


# ============================================================
# FEATURE SELECTION
# ============================================================

TARGETS = [
    f"flood_next_{h}h"
    for h in HORIZONS
]

EXCLUDED = set(
    TARGETS
    + [
        "timestamp",
        "historical_flood",
    ]
)

FEATURES = [
    c
    for c in df.columns
    if c not in EXCLUDED
]


print("\nFeatures:", len(FEATURES))

print("\nFirst features:")

for feature in FEATURES[:20]:
    print(
        " ",
        feature
    )


# ============================================================
# CONVERT FEATURES TO NUMERIC
# ============================================================

for column in FEATURES:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce"
    )


# ============================================================
# TIME-ORDERED SPLIT
# ============================================================
#
# IMPORTANT:
# We DO NOT randomly shuffle the time series.
#
# Training:
#   first 70%
#
# Validation:
#   next 15%
#
# Test:
#   final 15%
#
# This prevents future information leaking backwards.
# ============================================================

n = len(df)

train_end = int(
    n * 0.70
)

val_end = int(
    n * 0.85
)

train_df = df.iloc[
    :train_end
].copy()

val_df = df.iloc[
    train_end:val_end
].copy()

test_df = df.iloc[
    val_end:
].copy()


print("\n" + "=" * 80)
print("TIME-BASED DATA SPLIT")
print("=" * 80)

print(
    "Training:",
    len(train_df),
    train_df["timestamp"].min(),
    "->",
    train_df["timestamp"].max()
)

print(
    "Validation:",
    len(val_df),
    val_df["timestamp"].min(),
    "->",
    val_df["timestamp"].max()
)

print(
    "Testing:",
    len(test_df),
    test_df["timestamp"].min(),
    "->",
    test_df["timestamp"].max()
)


# ============================================================
# MODEL PARAMETERS
# ============================================================

MODEL_PARAMS = {
    "n_estimators": 300,
    "max_depth": 18,
    "min_samples_leaf": 3,
    "class_weight": "balanced",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}


# ============================================================
# METADATA
# ============================================================

metadata = {
    "project": "FloodWatch",
    "model_type": "RandomForestClassifier",
    "task": "future flood forecasting",
    "features": FEATURES,
    "horizons_hours": HORIZONS,
    "split": {
        "method": "chronological",
        "train": 0.70,
        "validation": 0.15,
        "test": 0.15,
    },
    "models": {},
}


# ============================================================
# TRAIN EACH FORECAST HORIZON
# ============================================================

for horizon in HORIZONS:

    print("\n" + "=" * 80)
    print(
        f"TRAINING {horizon}-HOUR FORECAST MODEL"
    )
    print("=" * 80)

    target = (
        f"flood_next_{horizon}h"
    )

    # --------------------------------------------------------
    # X / y
    # --------------------------------------------------------

    X_train = train_df[
        FEATURES
    ]

    y_train = train_df[
        target
    ].astype(int)

    X_val = val_df[
        FEATURES
    ]

    y_val = val_df[
        target
    ].astype(int)

    X_test = test_df[
        FEATURES
    ]

    y_test = test_df[
        target
    ].astype(int)

    print(
        "\nTraining positives:",
        int(y_train.sum())
    )

    print(
        "Validation positives:",
        int(y_val.sum())
    )

    print(
        "Test positives:",
        int(y_test.sum())
    )

    # --------------------------------------------------------
    # IMPUTER
    # --------------------------------------------------------

    imputer = SimpleImputer(
        strategy="median"
    )

    X_train_i = imputer.fit_transform(
        X_train
    )

    X_val_i = imputer.transform(
        X_val
    )

    X_test_i = imputer.transform(
        X_test
    )

    # --------------------------------------------------------
    # RANDOM FOREST
    # --------------------------------------------------------

    model = RandomForestClassifier(
        **MODEL_PARAMS
    )

    print(
        "\nTraining Random Forest..."
    )

    model.fit(
        X_train_i,
        y_train
    )

    print(
        "Training complete."
    )

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    val_probability = (
        model.predict_proba(
            X_val_i
        )[:, 1]
    )

    val_prediction = (
        val_probability >= 0.50
    ).astype(int)

    # --------------------------------------------------------
    # TEST
    # --------------------------------------------------------

    test_probability = (
        model.predict_proba(
            X_test_i
        )[:, 1]
    )

    test_prediction = (
        test_probability >= 0.50
    ).astype(int)

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    metrics = {}

    metrics["validation"] = {
        "accuracy": float(
            accuracy_score(
                y_val,
                val_prediction
            )
        ),
        "precision": float(
            precision_score(
                y_val,
                val_prediction,
                zero_division=0
            )
        ),
        "recall": float(
            recall_score(
                y_val,
                val_prediction,
                zero_division=0
            )
        ),
        "f1": float(
            f1_score(
                y_val,
                val_prediction,
                zero_division=0
            )
        ),
    }

    if len(
        np.unique(y_val)
    ) == 2:

        metrics["validation"]["roc_auc"] = float(
            roc_auc_score(
                y_val,
                val_probability
            )
        )

    metrics["test"] = {
        "accuracy": float(
            accuracy_score(
                y_test,
                test_prediction
            )
        ),
        "precision": float(
            precision_score(
                y_test,
                test_prediction,
                zero_division=0
            )
        ),
        "recall": float(
            recall_score(
                y_test,
                test_prediction,
                zero_division=0
            )
        ),
        "f1": float(
            f1_score(
                y_test,
                test_prediction,
                zero_division=0
            )
        ),
    }

    if len(
        np.unique(y_test)
    ) == 2:

        metrics["test"]["roc_auc"] = float(
            roc_auc_score(
                y_test,
                test_probability
            )
        )

    metrics["test"]["confusion_matrix"] = (
        confusion_matrix(
            y_test,
            test_prediction
        ).tolist()
    )

    # --------------------------------------------------------
    # PRINT RESULTS
    # --------------------------------------------------------

    print("\nVALIDATION RESULTS")

    for key, value in metrics[
        "validation"
    ].items():

        print(
            f"{key}: {value:.4f}"
            if isinstance(value, float)
            else f"{key}: {value}"
        )

    print("\nTEST RESULTS")

    for key, value in metrics[
        "test"
    ].items():

        if isinstance(value, float):

            print(
                f"{key}: {value:.4f}"
            )

        else:

            print(
                f"{key}: {value}"
            )

    # --------------------------------------------------------
    # FEATURE IMPORTANCE
    # --------------------------------------------------------

    importance = pd.DataFrame(
        {
            "feature": FEATURES,
            "importance": (
                model.feature_importances_
            ),
        }
    ).sort_values(
        "importance",
        ascending=False
    )

    print(
        "\nTop 15 important features:"
    )

    print(
        importance.head(15).to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # SAVE MODEL
    # --------------------------------------------------------

    model_path = (
        MODEL_DIR
        / f"flood_forecast_{horizon}h.pkl"
    )

    imputer_path = (
        MODEL_DIR
        / f"flood_forecast_{horizon}h_imputer.pkl"
    )

    importance_path = (
        MODEL_DIR
        / f"flood_forecast_{horizon}h_feature_importance.csv"
    )

    joblib.dump(
        model,
        model_path
    )

    joblib.dump(
        imputer,
        imputer_path
    )

    importance.to_csv(
        importance_path,
        index=False
    )

    print(
        "\nSaved:",
        model_path.name
    )

    # --------------------------------------------------------
    # STORE METADATA
    # --------------------------------------------------------

    metadata["models"][
        f"{horizon}h"
    ] = {
        "target": target,
        "model": model_path.name,
        "imputer": imputer_path.name,
        "metrics": metrics,
        "top_features": (
            importance
            .head(15)
            .to_dict(
                orient="records"
            )
        ),
    }


# ============================================================
# SAVE METADATA
# ============================================================

metadata_path = (
    MODEL_DIR
    / "flood_forecast_metadata.json"
)

metadata_path.write_text(
    json.dumps(
        metadata,
        indent=2
    ),
    encoding="utf-8"
)


# ============================================================
# COMPLETE
# ============================================================

print("\n" + "=" * 80)
print("ALL FORECAST MODELS TRAINED")
print("=" * 80)

print(
    "\nModels saved in:"
)

print(
    MODEL_DIR
)

print(
    "\nMetadata:"
)

print(
    metadata_path
)

print(
    "\nNEXT STEP:"
)

print(
    "Run predict_flood_forecast.py"
)

print("=" * 80)