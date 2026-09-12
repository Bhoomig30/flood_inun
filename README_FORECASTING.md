# FloodWatch Future Flood Forecasting

This pipeline adds a **temporal future-event forecasting model** to the existing project.

## Existing model vs new model

The existing 12-feature Random Forest predicts:

`Sentinel-1 + DEM + WorldCover + river features -> flood/non-flood pixel`

This new model predicts:

`historical rainfall + river discharge -> flood event within 6/12/24 hours`

These are deliberately separate tasks.

## Run order

From the `ml` directory:

```powershell
python .\src\build_forecast_dataset.py
```

Then inspect:

```text
ml\data\forecast\forecast_dataset.csv
ml\data\forecast\flood_events.csv
```

If the dataset contains enough positive future flood events, train:

```powershell
python .\src\train_flood_forecast.py
```

Then predict:

```powershell
python .\src\predict_future_flood.py
```

## Important scientific rule

Do NOT train if there are too few dated flood events.

A high accuracy number from a dataset with only a handful of flood events would be misleading.

The train/validation/test split is chronological, not random, to reduce temporal leakage.

## What must eventually be added for a production/live system

1. A reliable live rainfall feed.
2. A reliable live river-level/discharge feed.
3. More dated flood events across multiple years and regions.
4. A properly spatially matched flood-event target.
5. Calibration and threshold selection on an independent test period.
6. Monitoring and model retraining.
7. Clear separation between model predictions and official warnings.
