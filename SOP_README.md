---
title: "SOP: Running the AVITI Read QC Pipeline"
author: "Dan Parsons"
date: "`14.04.2026`"
output:
  html_document:
    toc: true
    toc_depth: 2
    toc_float: true
    theme: flatly
    highlight: tango
---

```{r setup, include=FALSE}
knitr::opts_chunk$set(echo = TRUE, eval = FALSE)
```

---

## Overview

This SOP describes how to configure and run the `aviti_read_qc_pipeline` — a Snakemake-based
pipeline for QC of raw, basecalled, and demultiplexed AVITI24 sequencing data. The pipeline
merges lane replicates, runs fastp trimming, falco (FastQC) reporting, and seqkit stats, and
aggregates everything into a single MultiQC report.

**Prerequisites:** conda must be installed and the repository must be cloned before starting.

---

## Step 1 — Locate your inputs

Confirm you have the following before proceeding:

- The run's `RunManifest.csv`
- The parent `Samples/` directory containing per-sample FASTQ subdirectories

FASTQ files must follow this naming convention:

```
{SampleName}_R1.fastq.gz
{SampleName}_R2.fastq.gz
```

> **Note:** PhiX entries and Unassigned reads are automatically excluded by the pipeline.

---

## Step 2 — Create and activate the conda environment

Run these commands once per installation. Skip if the environment already exists.

```{bash}
# Create the environment from the provided YAML
conda env create -f aviti_read_qc_pipeline.yaml

# Activate it
conda activate aviti_read_qc_pipeline

# Verify key dependencies
snakemake --version   # expected: 9.9.0
fastp --version       # expected: 1.3.1
```

---

## Step 3 — Configure the run

Copy the example config and populate it for your run:

```{bash}
cp config/config.yaml.example config/config.yaml
```

Open `config/config.yaml` and fill in the following required fields:

| Parameter | Description |
|---|---|
| `run_name` | Unique identifier for this run (used in output filenames) |
| `run_manifest` | Path to the `RunManifest.csv` |
| `samples_dir` | Path to the parent directory containing FASTQ files |
| `output_dir` | Directory where all outputs will be written |
| `adapter_r1` | Adapter sequence for forward reads |
| `adapter_r2` | Adapter sequence for reverse reads |

Adjust fastp parameters if needed — defaults are appropriate for most AVITI runs.

---

## Step 4 — Dry run

Always perform a dry run before submitting to SLURM to catch configuration errors early:

```{bash}
conda activate aviti_read_qc_pipeline
snakemake -n --quiet
```

Check that:

- The printed job list looks correct
- Sample counts match your expectations
- `logs/sample_manifest.log` contains no unexpected grouping warnings

> If sample grouping looks wrong (e.g. unexpected merging of unrelated samples), review the
> Index1 + Index2 pairs in your `RunManifest.csv` before proceeding.

---

## Step 5 — Submit to SLURM

```{bash}
sbatch aviti_read_qc_pipeline.slurm
```

Monitor job progress:

```{bash}
squeue -u $USER
```

Per-rule logs are written to `logs/<rule>/`. If a job fails, check the relevant log file there first.

> **Before submitting:** ensure the `source` line inside `aviti_read_qc_pipeline.sh` correctly
> points to your `conda.sh`, and that your NHM email address is set for SLURM notifications.

---

## Step 6 — Review outputs

Once the pipeline completes, review the following:

**MultiQC report** — open in a browser:
```
multiqc_report/{run_name}_multiqc_report.html
```

**Per-sample fastp summary CSV:**
```
02_fastp/{run_name}_fastp_summary.csv
```

Flag any samples meeting the following criteria for review:

- Duplication rate **> 20%**
- Post-filter read count **< 1 million**
- Q30 rate **< 80%**

---

## Step 7 — Archive

Once downstream analysis inputs are confirmed:

```{bash}
# Compress the output directory
zip -r {run_name}_outputs.zip output_dir/

# Transfer to appropriate project storage
# (update path as needed)
cp {run_name}_outputs.zip /path/to/project/storage/
```

> Raw merged FASTQ files in `00_lane_merge/` can be deleted once you have confirmed
> they are no longer needed as pipeline inputs.

---

## Quick reference: expected output structure

```
output_dir/
├── 00_lane_merge/          # Lane-concatenated FASTQs
├── 01_pre_qc/              # falco reports (pre-fastp)
├── 02_fastp/               # Trimmed reads, fastp HTML/JSON, summary CSV
├── 03_post_qc/             # falco reports (post-fastp)
├── 04_seqkit/              # seqkit stats per sample
├── multiqc_report/         # Aggregated MultiQC HTML report
└── logs/                   # Per-rule logs and sample_manifest.log
```

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| FASTQ files not found | Naming convention mismatch | Check files are named `{Sample}_R1.fastq.gz` |
| Unexpected sample grouping | Duplicate Index1+Index2 pairs | Review `RunManifest.csv`; check `sample_manifest.log` |
| conda activation fails in SLURM | Wrong `source` path | Edit the `source` line in `aviti_read_qc_pipeline.sh` |
| Dry run shows 0 jobs | Config path errors | Check all paths in `config/config.yaml` exist |
| MultiQC report missing samples | Rule failed upstream | Check `logs/` for the failing rule |

---

*Pipeline written by Dan Parsons for NHMUK Molecular Biology Laboratories.*
