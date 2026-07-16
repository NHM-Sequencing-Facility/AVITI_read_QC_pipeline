#!/bin/bash
#SBATCH --job-name=aviti_read_qc_pipeline
#SBATCH --partition=day
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err


# Set path and activate conda env
source /home/$USER/miniconda3/etc/profile.d/conda.sh

conda activate aviti_read_qc_pipeline


# Unlock pipeline dir
snakemake \
    --snakefile workflow/Snakefile \
    --configfile config/config.yaml \
    --profile profiles/slurm \
    --unlock

# Run pipeline
snakemake \
    --snakefile workflow/Snakefile \
    --configfile config/config.yaml \
    --profile profiles/slurm \
    --rerun-incomplete
