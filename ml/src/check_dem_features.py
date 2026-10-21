from pathlib import Path
import numpy as np
import rasterio


ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"
DEM_DIR = ML_DIR / "data" / "dem_features"


print("=" * 80)
print("DEM FEATURE VERIFICATION")
print("=" * 80)

print("\nImage directory:")
print(IMAGE_DIR)

print("\nDEM directory:")
print(DEM_DIR)


images = sorted(IMAGE_DIR.glob("*_image.tif"))

print("\nSatellite images:", len(images))


valid = 0
invalid = 0
missing = 0
empty = 0


for index, image_path in enumerate(images, start=1):

    scene_id = image_path.stem.replace("_image", "")
    dem_path = DEM_DIR / f"{scene_id}_dem.tif"

    if not dem_path.exists():

        print(f"\n[{index}/{len(images)}] {scene_id}")
        print("  ❌ DEM missing")

        missing += 1
        invalid += 1
        continue


    try:

        with rasterio.open(image_path) as image, \
             rasterio.open(dem_path) as dem:

            problems = []

            # ------------------------------------------------
            # SIZE
            # ------------------------------------------------

            if (
                image.width != dem.width
                or image.height != dem.height
            ):

                problems.append(
                    f"size mismatch "
                    f"{image.width}x{image.height} "
                    f"vs "
                    f"{dem.width}x{dem.height}"
                )


            # ------------------------------------------------
            # CRS
            # ------------------------------------------------

            if image.crs != dem.crs:

                problems.append(
                    f"CRS mismatch "
                    f"{image.crs} vs {dem.crs}"
                )


            # ------------------------------------------------
            # TRANSFORM
            # ------------------------------------------------

            if not np.allclose(
                image.transform,
                dem.transform,
                atol=1e-10
            ):

                problems.append(
                    "transform mismatch"
                )


            # ------------------------------------------------
            # BOUNDS
            # ------------------------------------------------

            if not np.allclose(
                [
                    image.bounds.left,
                    image.bounds.bottom,
                    image.bounds.right,
                    image.bounds.top
                ],
                [
                    dem.bounds.left,
                    dem.bounds.bottom,
                    dem.bounds.right,
                    dem.bounds.top
                ],
                atol=1e-8
            ):

                problems.append(
                    "bounds mismatch"
                )


            # ------------------------------------------------
            # DEM VALUES
            # ------------------------------------------------

            data = dem.read(1)

            valid_values = data[
                np.isfinite(data)
            ]


            if len(valid_values) == 0:

                problems.append(
                    "no valid elevation values"
                )

                empty += 1


            else:

                dem_min = float(
                    np.min(valid_values)
                )

                dem_max = float(
                    np.max(valid_values)
                )

                dem_mean = float(
                    np.mean(valid_values)
                )


            # ------------------------------------------------
            # RESULT
            # ------------------------------------------------

            if problems:

                print(
                    f"\n[{index}/{len(images)}] "
                    f"{scene_id}"
                )

                for problem in problems:

                    print(
                        "  ❌",
                        problem
                    )

                invalid += 1

            else:

                valid += 1

                if index <= 5:

                    print(
                        f"\n[{index}/{len(images)}] "
                        f"{scene_id}"
                    )

                    print(
                        "  Size:",
                        f"{dem.width} × {dem.height}"
                    )

                    print(
                        "  CRS:",
                        dem.crs
                    )

                    print(
                        "  Elevation min:",
                        f"{dem_min:.2f} m"
                    )

                    print(
                        "  Elevation max:",
                        f"{dem_max:.2f} m"
                    )

                    print(
                        "  Elevation mean:",
                        f"{dem_mean:.2f} m"
                    )

                    print(
                        "  ✓ Valid"
                    )


    except Exception as e:

        print(
            f"\n[{index}/{len(images)}] "
            f"{scene_id}"
        )

        print(
            "  ❌ Error:",
            e
        )

        invalid += 1


# ============================================================
# FINAL RESULT
# ============================================================

print("\n")
print("=" * 80)
print("FINAL DEM VERIFICATION")
print("=" * 80)

print(
    "\nTotal scenes:",
    len(images)
)

print(
    "Valid DEM scenes:",
    valid
)

print(
    "Invalid scenes:",
    invalid
)

print(
    "Missing DEMs:",
    missing
)

print(
    "Empty DEMs:",
    empty
)


if (
    valid == len(images)
    and invalid == 0
    and missing == 0
    and empty == 0
):

    print("\n")
    print(
        "✅ DEM FEATURES ARE VALID"
    )

    print(
        "\nAll DEMs:"
    )

    print(
        "  ✓ exist"
    )

    print(
        "  ✓ have matching dimensions"
    )

    print(
        "  ✓ have matching CRS"
    )

    print(
        "  ✓ have matching transforms"
    )

    print(
        "  ✓ have matching bounds"
    )

    print(
        "  ✓ contain valid elevation data"
    )

else:

    print("\n")
    print(
        "⚠ DEM VERIFICATION FAILED"
    )

    print(
        "Fix the reported scenes before proceeding."
    )