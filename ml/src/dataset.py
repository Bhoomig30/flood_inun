# from pathlib import Path

# import numpy as np
# import torch
# from torch.utils.data import Dataset
# import rasterio


# class FloodDataset(Dataset):

#     def __init__(self, split_file):

#         self.ml_dir = Path(__file__).resolve().parent.parent

#         self.image_dir = self.ml_dir / "data" / "images"
#         self.label_dir = self.ml_dir / "data" / "labels"
#         self.split_dir = self.ml_dir / "data" / "split"

#         split_path = self.split_dir / split_file

#         if not split_path.exists():
#             raise FileNotFoundError(
#                 f"Split file not found: {split_path}"
#             )

#         # Read sample IDs
#         self.ids = [
#             line.strip()
#             for line in split_path.read_text().splitlines()
#             if line.strip()
#         ]

#         print(f"{split_file}: {len(self.ids)} samples")

#     def __len__(self):
#         return len(self.ids)

#     def __getitem__(self, index):

#         sample_id = self.ids[index]

#         image_path = (
#             self.image_dir /
#             f"{sample_id}_image.tif"
#         )

#         label_path = (
#             self.label_dir /
#             f"{sample_id}_label.tif"
#         )

#         # -----------------------------
#         # Load image
#         # -----------------------------

#         with rasterio.open(image_path) as src:
#             image = src.read().astype(np.float32)

#         # Shape:
#         # (8, 512, 512)

#         # -----------------------------
#         # Load label
#         # -----------------------------

#         with rasterio.open(label_path) as src:
#             label = src.read(1)

#         # -----------------------------
#         # Handle invalid values
#         # -----------------------------

#         image = np.nan_to_num(
#             image,
#             nan=0.0,
#             posinf=0.0,
#             neginf=0.0
#         )

#         # -----------------------------
#         # Normalize each channel
#         # -----------------------------

#         for c in range(image.shape[0]):

#             band = image[c]

#             mean = band.mean()
#             std = band.std()

#             if std > 0:

#                 image[c] = (
#                     band - mean
#                 ) / std

#             else:

#                 image[c] = band - mean

#         # -----------------------------
#         # Convert label
#         #
#         # -1 = ignore
#         #  0 = non-flood
#         #  1 = flood
#         # -----------------------------

#         label = label.astype(np.int64)

#         # Keep -1 because we will use
#         # ignore_index=-1 during training.

#         # -----------------------------
#         # Convert to PyTorch tensors
#         # -----------------------------

#         image = torch.from_numpy(image)

#         label = torch.from_numpy(label)

#         return image, label
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset
import rasterio


class FloodDataset(Dataset):

    def __init__(self, split_file):

        self.ml_dir = Path(__file__).resolve().parent.parent

        self.image_dir = self.ml_dir / "data" / "images"
        self.label_dir = self.ml_dir / "data" / "labels"
        self.split_dir = self.ml_dir / "data" / "split"

        split_path = self.split_dir / split_file

        if not split_path.exists():
            raise FileNotFoundError(
                f"Split file not found: {split_path}"
            )

        self.ids = [
            line.strip()
            for line in split_path.read_text().splitlines()
            if line.strip()
        ]

        print(f"{split_file}: {len(self.ids)} samples")


    def __len__(self):
        return len(self.ids)


    def __getitem__(self, index):

        sample_id = self.ids[index]

        image_path = (
            self.image_dir /
            f"{sample_id}_image.tif"
        )

        label_path = (
            self.label_dir /
            f"{sample_id}_label.tif"
        )


        # ====================================================
        # LOAD IMAGE
        # ====================================================

        with rasterio.open(image_path) as src:
            image = src.read().astype(np.float32)


        # ====================================================
        # LOAD LABEL
        # ====================================================

        with rasterio.open(label_path) as src:
            label = src.read(1)


        # ====================================================
        # CLEAN IMAGE
        # ====================================================

        image = np.nan_to_num(
            image,
            nan=0.0,
            posinf=0.0,
            neginf=0.0
        )


        # ====================================================
        # ROBUST NORMALIZATION
        # ====================================================
        #
        # Instead of mean/std normalization, use percentile
        # clipping. This is more stable for remote-sensing data.
        #

        for c in range(image.shape[0]):

            band = image[c]

            low = np.percentile(
                band,
                2
            )

            high = np.percentile(
                band,
                98
            )

            if high > low:

                band = np.clip(
                    band,
                    low,
                    high
                )

                band = (
                    band - low
                ) / (
                    high - low
                )

            else:

                band = np.zeros_like(
                    band
                )


            image[c] = band


        # ====================================================
        # FINAL SAFETY CHECK
        # ====================================================

        image = np.nan_to_num(
            image,
            nan=0.0,
            posinf=1.0,
            neginf=0.0
        )


        # ====================================================
        # LABEL
        # ====================================================

        label = label.astype(
            np.int64
        )


        # ====================================================
        # TENSORS
        # ====================================================

        image = torch.from_numpy(
            image.copy()
        )

        label = torch.from_numpy(
            label.copy()
        )


        return image, label