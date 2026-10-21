#!/usr/bin/env python3
"""
Inventory and download the project's Hugging Face dataset.

  python ml/hf_data.py inventory
  python ml/hf_data.py download --pattern "ml/data/forecast/*"
  python ml/hf_data.py download
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import HF_REPO_ID, HF_REPO_TYPE, MANIFEST_FILE, PROJECT_ROOT  # noqa: E402


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def inventory(depth):
    from huggingface_hub import HfApi
    info = HfApi().dataset_info(HF_REPO_ID, files_metadata=True)
    files = [(s.rfilename, s.size or 0) for s in info.siblings]
    groups = defaultdict(lambda: {"files": 0, "bytes": 0, "ext": defaultdict(int)})
    for name, size in files:
        parts = name.split("/")
        key = "/".join(parts[:depth]) if len(parts) > depth else "/".join(parts[:-1]) or "(root)"
        g = groups[key]
        g["files"] += 1
        g["bytes"] += size
        g["ext"][Path(name).suffix.lower() or "(none)"] += 1

    print(f"\nRepo: {HF_REPO_ID}   files: {len(files):,}   total: {human(sum(s for _, s in files))}\n")
    print(f"{'folder':58s} {'files':>8s} {'size':>10s}  extensions")
    print("-" * 100)
    for k in sorted(groups):
        g = groups[k]
        ext = ", ".join(f"{e}:{c}" for e, c in sorted(g["ext"].items(), key=lambda x: -x[1])[:4])
        print(f"{k:58s} {g['files']:8,d} {human(g['bytes']):>10s}  {ext}")

    MANIFEST_FILE.write_text(json.dumps(
        {"repo": HF_REPO_ID, "files": [{"path": n, "bytes": s} for n, s in sorted(files)]}, indent=1))
    print(f"\nFull file list saved -> {MANIFEST_FILE}")


def download(pattern):
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=HF_REPO_ID, repo_type=HF_REPO_TYPE, local_dir=str(PROJECT_ROOT),
                      allow_patterns=pattern if pattern else None)
    print(f"Downloaded into {PROJECT_ROOT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("inventory"); a.add_argument("--depth", type=int, default=3)
    d = sub.add_parser("download"); d.add_argument("--pattern", action="append")
    args = ap.parse_args()
    inventory(args.depth) if args.cmd == "inventory" else download(args.pattern)