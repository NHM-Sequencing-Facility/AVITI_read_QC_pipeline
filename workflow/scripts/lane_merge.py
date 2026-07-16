#!/usr/bin/env python3
"""
lane_merge.py
=============
Merge (concatenate) R1 and R2 FASTQ files across lanes for a single sample.

Called by the lane_merge Snakemake rule. Accepts all parameters via CLI so
the rule can be submitted as a proper cluster job.

Usage:
    python lane_merge.py \
        --r1 file1_R1.fastq.gz [file2_R1.fastq.gz ...] \
        --r2 file1_R2.fastq.gz [file2_R2.fastq.gz ...] \
        --out-r1 /path/to/output_R1.fastq.gz \
        --out-r2 /path/to/output_R2.fastq.gz \
        --log /path/to/sample.log \
        --sample SampleName \
        --lane-names Pan1 Pan1a \
        --index1 TGACAACC --index2 GTCAACAG \
        --lane-merge-enabled true
"""

import argparse
import os
import shutil
import sys
from datetime import datetime


def str2bool(value):
    """Argparse-friendly bool parser (accepts true/false/1/0/yes/no/on/off)."""
    if isinstance(value, bool):
        return value
    v = value.strip().lower()
    if v in ("yes", "true", "t", "1", "on"):
        return True
    if v in ("no", "false", "f", "0", "off"):
        return False
    raise argparse.ArgumentTypeError(f"Boolean value expected, got: {value!r}")


def parse_args():
    p = argparse.ArgumentParser(description="Lane merge for QC pipeline")
    p.add_argument("--r1", nargs="+", required=True,
                   help="Input R1 fastq.gz files (one per lane, in order)")
    p.add_argument("--r2", nargs="+", required=True,
                   help="Input R2 fastq.gz files (one per lane, in order)")
    p.add_argument("--out-r1", required=True,
                   help="Output merged R1 fastq.gz path")
    p.add_argument("--out-r2", required=True,
                   help="Output merged R2 fastq.gz path")
    p.add_argument("--log", required=True,
                   help="Path to write the merge log")
    p.add_argument("--sample", required=True,
                   help="Base sample name")
    p.add_argument("--lane-names", nargs="+", default=[],
                   help="Per-lane sample names from manifest")
    # NOTE: index1/index2 are now two independent, optional string arguments
    # rather than a single `nargs=2` pair. Single-indexed runs (e.g. AVITI
    # manifests with no Index2 column) legitimately have an empty Index2, and
    # an empty string interpolated unquoted into a shell command disappears
    # entirely — which previously left argparse one token short for
    # `--index-key` (which required exactly two values) and crashed with
    # "expected 2 arguments". Splitting into two flags means each one is
    # valid on its own, including when empty.
    p.add_argument("--index1", default="",
                   help="Index1 for this sample group (empty string allowed)")
    p.add_argument("--index2", default="",
                   help="Index2 for this sample group; empty for single-indexed runs")
    p.add_argument("--lane-merge-enabled", type=str2bool, default=True,
                   help="If false, skip real lane merging: single-lane samples are "
                        "symlinked straight through instead of copied, and "
                        "multi-lane samples raise an error (they cannot be "
                        "processed without merging).")
    return p.parse_args()


def write_log(fh, msg):
    fh.write(msg + "\n")
    fh.flush()


def concatenate_files(in_paths, out_path, tag, log_fh):
    """Atomically concatenate in_paths → out_path via a .tmp intermediate."""
    tmp_path = out_path + ".tmp"
    write_log(log_fh, f"Writing {tag} → {out_path}")
    try:
        with open(tmp_path, "wb") as out_fh:
            for in_path in in_paths:
                write_log(log_fh, f"  Appending: {in_path}")
                with open(in_path, "rb") as in_fh:
                    shutil.copyfileobj(in_fh, out_fh)
        os.rename(tmp_path, out_path)
        size_gb = os.path.getsize(out_path) / (1024 ** 3)
        write_log(log_fh, f"  Done. Output size: {size_gb:.2f} GB\n")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        write_log(log_fh, f"ERROR during concatenation of {tag}: {e}")
        raise


def symlink_files(src_r1, src_r2, out_r1, out_r2, log_fh):
    """Symlink single-lane inputs straight through (used when lane_merge is disabled)."""
    for src, dst, tag in ((src_r1, out_r1, "R1"), (src_r2, out_r2, "R2")):
        if os.path.lexists(dst):
            os.remove(dst)
        abs_src = os.path.abspath(src)
        os.symlink(abs_src, dst)
        write_log(log_fh, f"  Symlinked {tag}: {dst} -> {abs_src}")


def main():
    args = parse_args()

    # Create output and log directories
    os.makedirs(os.path.dirname(os.path.abspath(args.out_r1)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)

    n_lanes = len(args.r1)

    with open(args.log, "w") as log:
        write_log(log, "=" * 60)
        write_log(log, f"Lane merge: {args.sample}")
        write_log(log, f"Started   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        write_log(log, f"Index pair: ({args.index1!r}, {args.index2!r})")
        write_log(log, f"Lane names: {args.lane_names}")
        write_log(log, f"N lanes   : {n_lanes}")
        write_log(log, f"lane_merge enabled: {args.lane_merge_enabled}")
        write_log(log, "=" * 60 + "\n")

        write_log(log, "Input R1 files:")
        for f in args.r1:
            write_log(log, f"  {f}")
        write_log(log, "Input R2 files:")
        for f in args.r2:
            write_log(log, f"  {f}")
        write_log(log, "")

        # Validate all inputs exist
        for f in args.r1 + args.r2:
            if not os.path.exists(f):
                msg = f"ERROR: Input file not found: {f}"
                write_log(log, msg)
                sys.stderr.write(msg + "\n")
                sys.exit(1)

        # Check for empty inputs
        empty = [f for f in args.r1 + args.r2 if os.path.getsize(f) == 0]
        if empty:
            write_log(log, "WARNING: One or more input files are empty:")
            for f in empty:
                write_log(log, f"  {f}")
            write_log(log, "Creating empty placeholder outputs.")
            write_log(log, "Downstream QC steps will detect and skip this sample.")
            open(args.out_r1, "w").close()
            open(args.out_r2, "w").close()
            write_log(log, f"Placeholder R1: {args.out_r1}")
            write_log(log, f"Placeholder R2: {args.out_r2}")
            write_log(log, f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            return

        if not args.lane_merge_enabled:
            write_log(log, "lane_merge step disabled via config (lane_merge.enabled: false).")
            if n_lanes > 1:
                msg = (
                    f"ERROR: Sample '{args.sample}' has {n_lanes} lanes but "
                    f"lane_merge is disabled. Multi-lane samples cannot be "
                    f"processed without merging — set lane_merge.enabled: true "
                    f"in config.yaml, or fix the manifest grouping."
                )
                write_log(log, msg)
                sys.stderr.write(msg + "\n")
                sys.exit(1)
            write_log(log, "Single lane — symlinking instead of copying (lane_merge disabled).")
            symlink_files(args.r1[0], args.r2[0], args.out_r1, args.out_r2, log)
        elif n_lanes == 1:
            write_log(log, "Single lane — copying directly (no concatenation).")
            shutil.copy2(args.r1[0], args.out_r1)
            shutil.copy2(args.r2[0], args.out_r2)
            write_log(log, f"Copied R1: {args.r1[0]} → {args.out_r1}")
            write_log(log, f"Copied R2: {args.r2[0]} → {args.out_r2}")
        else:
            write_log(log, f"Multi-lane ({n_lanes} lanes) — concatenating.\n")
            concatenate_files(args.r1, args.out_r1, "R1", log)
            concatenate_files(args.r2, args.out_r2, "R2", log)

        write_log(log, f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
