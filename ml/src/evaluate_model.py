from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from dataset import FloodDataset
from unet_small import UNetSmall


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parent.parent

MODEL_PATH = (
    ML_DIR
    / "models"
    / "flood_unet_baseline.pth"
)


# ============================================================
# DEVICE
# ============================================================

device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

print("=" * 70)
print("TESTING TRAINED FLOOD MODEL")
print("=" * 70)

print("\nDevice:", device)


# ============================================================
# TEST DATASET
# ============================================================

test_dataset = FloodDataset(
    "test.txt"
)

test_loader = DataLoader(
    test_dataset,
    batch_size=1,
    shuffle=False,
    num_workers=0
)

print(
    "\nTest samples:",
    len(test_dataset)
)


# ============================================================
# MODEL
# ============================================================

model = UNetSmall(
    in_channels=8,
    out_channels=2
)


# ============================================================
# LOAD CHECKPOINT
# ============================================================

print("\nLoading trained model...")

checkpoint = torch.load(
    MODEL_PATH,
    map_location=device
)

# Our train.py saved a dictionary.
if "model_state_dict" in checkpoint:

    model.load_state_dict(
        checkpoint["model_state_dict"]
    )

else:

    # Compatibility with a plain state_dict
    model.load_state_dict(
        checkpoint
    )


model = model.to(device)

model.eval()


print("✓ Model loaded")


# ============================================================
# LOSS
# ============================================================

criterion = nn.CrossEntropyLoss(
    ignore_index=-1
)


# ============================================================
# METRICS
# ============================================================

total_loss = 0.0

total_iou = 0.0

total_dice = 0.0

samples = 0


# ============================================================
# TEST
# ============================================================

with torch.no_grad():

    for index, (
        images,
        labels
    ) in enumerate(test_loader):

        images = images.to(device)

        labels = labels.to(device)


        # ----------------------------------------------------
        # Forward pass
        # ----------------------------------------------------

        outputs = model(images)


        # ----------------------------------------------------
        # Loss
        # ----------------------------------------------------

        loss = criterion(
            outputs,
            labels
        )


        if not torch.isfinite(loss):

            print(
                f"Skipping sample {index + 1}: "
                f"invalid loss"
            )

            continue


        # ----------------------------------------------------
        # Prediction
        # ----------------------------------------------------

        predictions = torch.argmax(
            outputs,
            dim=1
        )


        # ----------------------------------------------------
        # Valid pixels
        # ----------------------------------------------------

        valid = labels != -1


        pred = predictions[valid]

        actual = labels[valid]


        if pred.numel() == 0:

            continue


        # ----------------------------------------------------
        # Flood masks
        # ----------------------------------------------------

        pred_flood = (
            pred == 1
        )

        actual_flood = (
            actual == 1
        )


        # ----------------------------------------------------
        # Intersection
        # ----------------------------------------------------

        intersection = (
            pred_flood
            & actual_flood
        ).sum().item()


        pred_count = (
            pred_flood
            .sum()
            .item()
        )


        actual_count = (
            actual_flood
            .sum()
            .item()
        )


        # ----------------------------------------------------
        # Union
        # ----------------------------------------------------

        union = (
            pred_count
            + actual_count
            - intersection
        )


        # ----------------------------------------------------
        # IoU
        # ----------------------------------------------------

        if union == 0:

            iou = 1.0

        else:

            iou = (
                intersection
                / union
            )


        # ----------------------------------------------------
        # Dice
        # ----------------------------------------------------

        denominator = (
            pred_count
            + actual_count
        )


        if denominator == 0:

            dice = 1.0

        else:

            dice = (
                2.0
                * intersection
                / denominator
            )


        total_loss += loss.item()

        total_iou += iou

        total_dice += dice

        samples += 1


        # ----------------------------------------------------
        # Progress
        # ----------------------------------------------------

        if (
            index + 1
        ) % 10 == 0:

            print(
                f"Test sample "
                f"{index + 1}/"
                f"{len(test_loader)}"
            )


# ============================================================
# FINAL RESULTS
# ============================================================

print("\n")
print("=" * 70)
print("TEST RESULTS")
print("=" * 70)


if samples > 0:

    test_loss = (
        total_loss / samples
    )

    test_iou = (
        total_iou / samples
    )

    test_dice = (
        total_dice / samples
    )


    print(
        f"\nTest Loss : "
        f"{test_loss:.4f}"
    )

    print(
        f"Test IoU  : "
        f"{test_iou:.4f}"
    )

    print(
        f"Test Dice : "
        f"{test_dice:.4f}"
    )

else:

    print(
        "\nNo valid test samples."
    )


print("\n✓ Evaluation complete.")