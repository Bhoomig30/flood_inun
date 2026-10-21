from pathlib import Path
import random

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from dataset import FloodDataset
from unet_small import UNetSmall


# ============================================================
# SETTINGS
# ============================================================

EPOCHS = 5

BATCH_SIZE = 1

PATCH_SIZE = 256

LEARNING_RATE = 1e-5

SEED = 42


# ============================================================
# REPRODUCIBILITY
# ============================================================

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)


# ============================================================
# PROJECT PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parent.parent

MODEL_DIR = ML_DIR / "models"

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# DEVICE
# ============================================================

device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

print("=" * 70)
print("FLOOD MODEL TRAINING")
print("=" * 70)

print("\nDevice:", device)

if device.type == "cpu":
    print("CPU training enabled.")


# ============================================================
# DATASET
# ============================================================

print("\nLoading datasets...")

train_dataset = FloodDataset(
    "train.txt"
)

val_dataset = FloodDataset(
    "val.txt"
)

print(
    "\nTraining samples:",
    len(train_dataset)
)

print(
    "Validation samples:",
    len(val_dataset)
)


# ============================================================
# DATALOADERS
# ============================================================

train_loader = DataLoader(
    train_dataset,
    batch_size=BATCH_SIZE,
    shuffle=True,
    num_workers=0
)

val_loader = DataLoader(
    val_dataset,
    batch_size=BATCH_SIZE,
    shuffle=False,
    num_workers=0
)


# ============================================================
# MODEL
# ============================================================

print("\nCreating model...")

model = UNetSmall(
    in_channels=8,
    out_channels=2
)

model = model.to(device)


parameters = sum(
    p.numel()
    for p in model.parameters()
)

print(
    f"Model parameters: {parameters:,}"
)


# ============================================================
# LOSS
# ============================================================

# Labels:
#
# -1 = ignored/no-data
#  0 = non-flood
#  1 = flood

criterion = nn.CrossEntropyLoss(
    ignore_index=-1
)


# ============================================================
# OPTIMIZER
# ============================================================

optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=LEARNING_RATE,
    weight_decay=1e-4
)


# ============================================================
# RANDOM VALID PATCH
# ============================================================

def get_random_patch(image, label):

    _, height, width = image.shape

    # If image is smaller than requested patch,
    # return the complete image.
    if (
        height < PATCH_SIZE
        or width < PATCH_SIZE
    ):
        return image, label


    # Try multiple random locations.
    for _ in range(30):

        top = random.randint(
            0,
            height - PATCH_SIZE
        )

        left = random.randint(
            0,
            width - PATCH_SIZE
        )


        image_patch = image[
            :,
            top:top + PATCH_SIZE,
            left:left + PATCH_SIZE
        ]


        label_patch = label[
            top:top + PATCH_SIZE,
            left:left + PATCH_SIZE
        ]


        # Count valid pixels.
        valid_pixels = (
            label_patch != -1
        ).sum().item()


        # We need at least one valid pixel.
        if valid_pixels > 0:

            return (
                image_patch,
                label_patch
            )


    # --------------------------------------------------------
    # Fallback: center crop
    # --------------------------------------------------------

    top = (
        height - PATCH_SIZE
    ) // 2

    left = (
        width - PATCH_SIZE
    ) // 2


    return (
        image[
            :,
            top:top + PATCH_SIZE,
            left:left + PATCH_SIZE
        ],

        label[
            top:top + PATCH_SIZE,
            left:left + PATCH_SIZE
        ]
    )


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    predictions,
    labels
):

    # Ignore -1 pixels.
    valid = labels != -1

    predictions = predictions[valid]

    labels = labels[valid]


    if predictions.numel() == 0:

        return 0.0, 0.0


    # --------------------------------------------------------
    # Flood pixels
    # --------------------------------------------------------

    predicted_flood = (
        predictions == 1
    )

    actual_flood = (
        labels == 1
    )


    # --------------------------------------------------------
    # Intersection
    # --------------------------------------------------------

    intersection = (
        predicted_flood
        & actual_flood
    ).sum().item()


    # --------------------------------------------------------
    # Union
    # --------------------------------------------------------

    predicted_count = (
        predicted_flood
        .sum()
        .item()
    )

    actual_count = (
        actual_flood
        .sum()
        .item()
    )


    union = (
        predicted_count
        + actual_count
        - intersection
    )


    # --------------------------------------------------------
    # IoU
    # --------------------------------------------------------

    if union == 0:

        iou = 1.0

    else:

        iou = (
            intersection
            / union
        )


    # --------------------------------------------------------
    # Dice
    # --------------------------------------------------------

    denominator = (
        predicted_count
        + actual_count
    )


    if denominator == 0:

        dice = 1.0

    else:

        dice = (
            2.0 * intersection
            / denominator
        )


    return iou, dice


# ============================================================
# BEST MODEL
# ============================================================

best_iou = -1.0

best_dice = 0.0


# ============================================================
# TRAINING LOOP
# ============================================================

for epoch in range(EPOCHS):

    print("\n")
    print("=" * 70)

    print(
        f"EPOCH {epoch + 1}/{EPOCHS}"
    )

    print("=" * 70)


    # ========================================================
    # TRAIN
    # ========================================================

    model.train()


    total_train_loss = 0.0

    successful_batches = 0

    skipped_batches = 0


    for batch_index, (
        images,
        labels
    ) in enumerate(train_loader):


        # ----------------------------------------------------
        # Create valid random patches
        # ----------------------------------------------------

        patched_images = []

        patched_labels = []


        for image, label in zip(
            images,
            labels
        ):

            image_patch, label_patch = (
                get_random_patch(
                    image,
                    label
                )
            )


            patched_images.append(
                image_patch
            )

            patched_labels.append(
                label_patch
            )


        images = torch.stack(
            patched_images
        )

        labels = torch.stack(
            patched_labels
        )


        # ----------------------------------------------------
        # Move to device
        # ----------------------------------------------------

        images = images.to(
            device
        )

        labels = labels.to(
            device
        )


        # ----------------------------------------------------
        # Check input values
        # ----------------------------------------------------

        if not torch.isfinite(
            images
        ).all():

            print(
                f"Skipping batch "
                f"{batch_index + 1}: "
                f"invalid image values."
            )

            skipped_batches += 1

            continue


        # ----------------------------------------------------
        # Check labels
        # ----------------------------------------------------

        valid_pixels = (
            labels != -1
        )


        if valid_pixels.sum().item() == 0:

            print(
                f"Skipping batch "
                f"{batch_index + 1}: "
                f"no valid label pixels."
            )

            skipped_batches += 1

            continue


        # ----------------------------------------------------
        # Check labels are valid
        # ----------------------------------------------------

        invalid_labels = (
            (labels != -1)
            & (labels != 0)
            & (labels != 1)
        )


        if invalid_labels.any():

            print(
                f"Skipping batch "
                f"{batch_index + 1}: "
                f"invalid label values."
            )

            skipped_batches += 1

            continue


        # ----------------------------------------------------
        # Clear gradients
        # ----------------------------------------------------

        optimizer.zero_grad(
            set_to_none=True
        )


        # ----------------------------------------------------
        # Forward pass
        # ----------------------------------------------------

        outputs = model(
            images
        )


        # ----------------------------------------------------
        # Check model output
        # ----------------------------------------------------

        if not torch.isfinite(
            outputs
        ).all():

            print(
                f"Skipping batch "
                f"{batch_index + 1}: "
                f"model output became NaN/Inf."
            )

            skipped_batches += 1

            continue


        # ----------------------------------------------------
        # Loss
        # ----------------------------------------------------

        loss = criterion(
            outputs,
            labels
        )


        # ----------------------------------------------------
        # Check loss
        # ----------------------------------------------------

        if not torch.isfinite(
            loss
        ):

            print(
                f"Skipping batch "
                f"{batch_index + 1}: "
                f"loss became NaN/Inf."
            )

            skipped_batches += 1

            continue


        # ----------------------------------------------------
        # Backpropagation
        # ----------------------------------------------------

        loss.backward()


        # ----------------------------------------------------
        # Gradient clipping
        # ----------------------------------------------------

        torch.nn.utils.clip_grad_norm_(
            model.parameters(),
            max_norm=1.0
        )


        # ----------------------------------------------------
        # Optimizer update
        # ----------------------------------------------------

        optimizer.step()


        # ----------------------------------------------------
        # Record loss
        # ----------------------------------------------------

        total_train_loss += (
            loss.item()
        )

        successful_batches += 1


        # ----------------------------------------------------
        # Progress
        # ----------------------------------------------------

        if (
            batch_index + 1
        ) % 25 == 0:

            print(
                f"Batch "
                f"{batch_index + 1}/"
                f"{len(train_loader)} "
                f"Loss: "
                f"{loss.item():.4f}"
            )


    # ========================================================
    # TRAIN LOSS
    # ========================================================

    if successful_batches > 0:

        train_loss = (
            total_train_loss
            / successful_batches
        )

    else:

        train_loss = float("nan")


    # ========================================================
    # VALIDATION
    # ========================================================

    model.eval()


    total_val_loss = 0.0

    total_iou = 0.0

    total_dice = 0.0

    validation_batches = 0


    with torch.no_grad():

        for images, labels in val_loader:


            # ------------------------------------------------
            # Center crop
            # ------------------------------------------------

            _, _, height, width = (
                images.shape
            )


            if (
                height >= PATCH_SIZE
                and width >= PATCH_SIZE
            ):

                top = (
                    height - PATCH_SIZE
                ) // 2

                left = (
                    width - PATCH_SIZE
                ) // 2


                images = images[
                    :,
                    :,
                    top:top + PATCH_SIZE,
                    left:left + PATCH_SIZE
                ]


                labels = labels[
                    :,
                    top:top + PATCH_SIZE,
                    left:left + PATCH_SIZE
                ]


            # ------------------------------------------------
            # Move data
            # ------------------------------------------------

            images = images.to(
                device
            )

            labels = labels.to(
                device
            )


            # ------------------------------------------------
            # Ignore validation samples with no valid pixels
            # ------------------------------------------------

            valid_pixels = (
                labels != -1
            )


            if valid_pixels.sum().item() == 0:

                continue


            # ------------------------------------------------
            # Forward pass
            # ------------------------------------------------

            outputs = model(
                images
            )


            # ------------------------------------------------
            # Check output
            # ------------------------------------------------

            if not torch.isfinite(
                outputs
            ).all():

                continue


            # ------------------------------------------------
            # Validation loss
            # ------------------------------------------------

            loss = criterion(
                outputs,
                labels
            )


            if not torch.isfinite(
                loss
            ):

                continue


            total_val_loss += (
                loss.item()
            )


            # ------------------------------------------------
            # Prediction
            # ------------------------------------------------

            predictions = torch.argmax(
                outputs,
                dim=1
            )


            # ------------------------------------------------
            # Metrics
            # ------------------------------------------------

            iou, dice = calculate_metrics(
                predictions,
                labels
            )


            total_iou += iou

            total_dice += dice

            validation_batches += 1


    # ========================================================
    # VALIDATION RESULTS
    # ========================================================

    if validation_batches > 0:

        val_loss = (
            total_val_loss
            / validation_batches
        )

        val_iou = (
            total_iou
            / validation_batches
        )

        val_dice = (
            total_dice
            / validation_batches
        )

    else:

        val_loss = float("nan")

        val_iou = 0.0

        val_dice = 0.0


    # ========================================================
    # PRINT RESULTS
    # ========================================================

    print("\nResults:")

    print(
        f"Train Loss : "
        f"{train_loss:.4f}"
    )

    print(
        f"Val Loss   : "
        f"{val_loss:.4f}"
    )

    print(
        f"Val IoU    : "
        f"{val_iou:.4f}"
    )

    print(
        f"Val Dice   : "
        f"{val_dice:.4f}"
    )

    print(
        f"Skipped batches: "
        f"{skipped_batches}"
    )


    # ========================================================
    # SAVE BEST MODEL
    # ========================================================

    if (
        np.isfinite(val_iou)
        and val_iou > best_iou
    ):

        best_iou = val_iou

        best_dice = val_dice


        model_path = (
            MODEL_DIR
            / "flood_unet_baseline.pth"
        )


        torch.save(
            {
                "model_state_dict":
                    model.state_dict(),

                "epoch":
                    epoch + 1,

                "val_iou":
                    val_iou,

                "val_dice":
                    val_dice,

                "input_channels":
                    8,

                "patch_size":
                    PATCH_SIZE
            },
            model_path
        )


        print(
            "\n✓ Best model saved:"
        )

        print(
            model_path
        )


# ============================================================
# TRAINING COMPLETE
# ============================================================

print("\n")
print("=" * 70)
print("TRAINING COMPLETE")
print("=" * 70)


if best_iou >= 0:

    print(
        f"\nBest validation IoU: "
        f"{best_iou:.4f}"
    )

    print(
        f"Best validation Dice: "
        f"{best_dice:.4f}"
    )

else:

    print(
        "\nNo valid model checkpoint "
        "was produced."
    )


print("\nModel directory:")

print(MODEL_DIR)

print("\nDone!")