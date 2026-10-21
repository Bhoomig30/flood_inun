#!/usr/bin/env python3
"""
Assign every Sen1Floods11 tile to its flood EVENT / COUNTRY using the dataset's own
metadata polygons (not a loose lat/lon box), and rebuild the India scene list.

Why: the old india_scenes.txt came from a 67-98E / 5-38N bounding box, which also
catches Pakistan and Sri Lanka tiles (138 tiles instead of the ~68 true India tiles).

Outputs (in ml/data/):
  scene_events.csv   scene, split, iso, country, s1_date, lon, lat, how
  india_scenes.txt   strict India (ISO_CC == IND) tiles only, '<id>_image.tif' per line
                     (the previous file is kept as india_scenes_bbox_OLD.txt)

Needs the tile rasters to read their location. Small files are enough:
  python ml/hf_data.py download --pattern "ml/data/landcover_features/*"   (~8 MB)

Usage:  python ml/src/build_scene_events.py [--data-dir ml/data]
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import rasterio
from rasterio.warp import transform as warp_transform
from shapely.geometry import Point, shape

ML_DIR = Path(__file__).resolve().parents[1]
NEAREST_TOLERANCE_DEG = 1.0     # tile centre may sit just outside a coarse event polygon


def read_ids(path):
    return [x.strip().replace("_image.tif", "") for x in open(path, encoding="utf-8") if x.strip()]


def tile_centre(data_dir, sid):
    """Centre (lon, lat) of a tile, using the first small raster that exists."""
    for folder, suffix in (("landcover_features", "_landcover.tif"), ("dem_features", "_dem.tif"),
                           ("labels", "_label.tif"), ("images", "_image.tif")):
        p = data_dir / folder / f"{sid}{suffix}"
        if p.exists():
            with rasterio.open(p) as src:
                b, crs = src.bounds, src.crs
                cx, cy = (b.left + b.right) / 2, (b.bottom + b.top) / 2
                if crs is not None and crs.to_epsg() != 4326:
                    xs, ys = warp_transform(crs, "EPSG:4326", [cx], [cy])
                    cx, cy = xs[0], ys[0]
                return cx, cy
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ML_DIR / "data"))
    data_dir = Path(ap.parse_args().data_dir)

    meta = json.load(open(data_dir / "sen1_metadata" / "Sen1Floods11_Metadata.geojson", encoding="utf-8"))
    events = [(f["properties"], shape(f["geometry"])) for f in meta["features"]]

    split_of = {}
    for name in ("train", "val", "test"):
        for sid in read_ids(data_dir / "split" / f"{name}.txt"):
            split_of[sid] = name

    rows, missing = [], []
    for sid, split in split_of.items():
        c = tile_centre(data_dir, sid)
        if c is None:
            missing.append(sid)
            continue
        pt, hit, how = Point(c), None, "inside"
        for props, poly in events:
            if poly.contains(pt):
                hit = props
                break
        if hit is None:
            d, props = min(((poly.distance(pt), p) for p, poly in events), key=lambda x: x[0])
            if d <= NEAREST_TOLERANCE_DEG:
                hit, how = props, f"nearest({d:.2f}deg)"
        rows.append({"scene": sid, "split": split,
                     "iso": hit["ISO_CC"] if hit else "UNKNOWN",
                     "country": hit["location"] if hit else "UNKNOWN",
                     "s1_date": hit["s1_date"] if hit else "",
                     "lon": round(c[0], 5), "lat": round(c[1], 5), "how": how if hit else "no_match"})

    if missing:
        print(f"WARNING: {len(missing)} tiles had no raster to read (e.g. {missing[:3]}). "
              "Download ml/data/landcover_features first.")
    if not rows:
        sys.exit("No tiles located - nothing written.")

    out_csv = data_dir / "scene_events.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["iso"], r["scene"])))

    # ---- summary + self-check against the metadata's hand-labelled chip counts ----
    per = defaultdict(Counter)
    for r in rows:
        per[r["iso"]][r["split"]] += 1
    expected = {p["ISO_CC"]: p.get("val_chip") for p, _ in events}   # = hand-labelled chips per event
    print(f"\n{'event':10s} {'train':>6s} {'val':>5s} {'test':>5s} {'total':>6s} {'metadata':>9s}")
    for iso in sorted(per):
        c = per[iso]
        tot = sum(c.values())
        exp = expected.get(iso)
        flag = "" if exp is None or exp == tot else "  <-- differs from metadata"
        print(f"{iso:10s} {c['train']:6d} {c['val']:5d} {c['test']:5d} {tot:6d} {str(exp):>9s}{flag}")

    india = sorted(r["scene"] for r in rows if r["iso"] == "IND")
    old = data_dir / "india_scenes.txt"
    if old.exists() and not (data_dir / "india_scenes_bbox_OLD.txt").exists():
        old.rename(data_dir / "india_scenes_bbox_OLD.txt")
    (data_dir / "india_scenes.txt").write_text("".join(f"{s}_image.tif\n" for s in india), encoding="utf-8")
    sp = Counter(r["split"] for r in rows if r["iso"] == "IND")
    print(f"\nStrict India tiles: {len(india)}  (train {sp['train']}, val {sp['val']}, test {sp['test']})")
    print(f"Wrote {out_csv}\nWrote {data_dir / 'india_scenes.txt'}  (old list kept as india_scenes_bbox_OLD.txt)")


if __name__ == "__main__":
    main()
