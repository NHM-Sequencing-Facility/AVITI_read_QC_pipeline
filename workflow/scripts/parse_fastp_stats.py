#!/usr/bin/env python3

import argparse
import json
import csv
import os
import glob
import sys
import yaml


def parse_fastp_json(json_path):
    """Parse fastp JSON file and extract specified statistics."""
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)

        stats = {}

        # Before filtering stats
        bf = data['summary']['before_filtering']
        stats.update({
            'before_total_reads': bf['total_reads'],
            'before_total_bases': bf['total_bases'],
            'before_q20_bases': bf['q20_bases'],
            'before_q30_bases': bf['q30_bases'],
            'before_q20_rate': bf['q20_rate'],
            'before_q30_rate': bf['q30_rate'],
            'before_gc_content': bf['gc_content']
        })

        # After filtering stats
        af = data['summary']['after_filtering']
        stats.update({
            'after_total_reads': af['total_reads'],
            'after_total_bases': af['total_bases'],
            'after_q20_bases': af['q20_bases'],
            'after_q30_bases': af['q30_bases'],
            'after_q20_rate': af['q20_rate'],
            'after_q30_rate': af['q30_rate'],
            'after_gc_content': af['gc_content']
        })

        # Filtering result stats
        fr = data['filtering_result']
        stats.update({
            'passed_filter_reads': fr['passed_filter_reads'],
            'low_quality_reads': fr['low_quality_reads'],
            'too_many_N_reads': fr['too_many_N_reads'],
            'too_short_reads': fr['too_short_reads'],
            'too_long_reads': fr['too_long_reads']
        })

        # Duplication rate
        stats['duplication_rate'] = data['duplication']['rate']

        # Insert size peak
        stats['insert_size_peak'] = data['insert_size']['peak']

        return stats

    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        print(f"Error parsing {json_path}: {e}", file=sys.stderr)
        return None


def find_fastp_files(trimmed_data_paths):
    """Find all fastp JSON files in the specified directories.

    Supports both:
    1. Nested structure: trimmed_data/sample_name/sample_name.json
    2. Flat structure: directory/*.json (sample name from filename)
    """
    fastp_files = []

    for trimmed_data_path in trimmed_data_paths:
        if not os.path.exists(trimmed_data_path):
            print(f"Warning: Path does not exist: {trimmed_data_path}", file=sys.stderr)
            continue

        # First, look for JSON files directly in the directory (flat structure)
        json_pattern = os.path.join(trimmed_data_path, "*.json")
        direct_json_files = glob.glob(json_pattern)

        if direct_json_files:
            # Flat structure found
            for json_file in direct_json_files:
                sample_name = os.path.splitext(os.path.basename(json_file))[0]
                fastp_files.append((sample_name, json_file))
            print(f"Found {len(direct_json_files)} JSON files in flat structure at {trimmed_data_path}", file=sys.stderr)
        else:
            # Look for subdirectories (nested structure)
            try:
                subdirs = [d for d in os.listdir(trimmed_data_path)
                           if os.path.isdir(os.path.join(trimmed_data_path, d))]

                nested_found = 0
                for subdir in subdirs:
                    sample_name = subdir
                    json_pattern = os.path.join(trimmed_data_path, subdir, f"{sample_name}*.json")
                    matching_files = glob.glob(json_pattern)

                    if matching_files:
                        fastp_files.append((sample_name, matching_files[0]))
                        nested_found += 1
                    else:
                        print(f"Warning: No fastp JSON found for sample {sample_name} in {json_pattern}", file=sys.stderr)

                if nested_found > 0:
                    print(f"Found {nested_found} JSON files in nested structure at {trimmed_data_path}", file=sys.stderr)
                elif subdirs:
                    print(f"Warning: Found subdirectories but no matching JSON files at {trimmed_data_path}", file=sys.stderr)
                else:
                    print(f"Warning: No JSON files or subdirectories found at {trimmed_data_path}", file=sys.stderr)

            except PermissionError:
                print(f"Warning: Permission denied accessing {trimmed_data_path}", file=sys.stderr)

    return fastp_files


def write_general_stats_mqc(mqc_data, output_path):
    """Write a MultiQC custom-content YAML that injects accurate raw/final
    read and base counts into the General Statistics table.

    The bundled fastp module's "Reads After Filtering" column reports
    filtering_result.passed_filter_reads, which is measured BEFORE
    deduplication. This writes the true final counts (summary.after_filtering)
    alongside the raw input counts (summary.before_filtering), under our own
    column definitions/descriptions.
    """
    headers = [
        {"raw_reads": {
            "title": "Raw Reads",
            "description": "Total read count (R1+R2) in the input FASTQs, before any fastp filtering, trimming, or deduplication.",
            "suffix": " M",
            "format": "{:,.2f}",
            "scale": "Blues",
        }},
        {"raw_bases": {
            "title": "Raw Bases",
            "description": "Total base count (R1+R2) in the input FASTQs, before any fastp filtering, trimming, or deduplication.",
            "suffix": " Mb",
            "format": "{:,.2f}",
            "scale": "Purples",
        }},
        {"final_reads": {
            "title": "Reads After Filtering",
            "description": (
                "Total read count (R1+R2) in the final output FASTQs, after "
                "quality/length/adapter filtering AND deduplication (if "
                "--dedup is enabled). This is fastp's "
                "summary.after_filtering.total_reads, not "
                "filtering_result.passed_filter_reads (which is measured "
                "before dedup and is typically much higher)."
            ),
            "suffix": " M",
            "format": "{:,.2f}",
            "scale": "Greens",
        }},
        {"final_bases": {
            "title": "Bases After Filtering",
            "description": "Total base count (R1+R2) in the final output FASTQs, after all filtering and deduplication steps.",
            "suffix": " Mb",
            "format": "{:,.2f}",
            "scale": "Greens",
        }},
    ]

    payload = {
        "custom_data": {
            "fastp_read_base_summary": {
                "plot_type": "generalstats",
                "headers": headers,
                "data": mqc_data,
            }
        }
    }

    with open(output_path, 'w') as fh:
        yaml.dump(payload, fh, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(
        description="Parse fastp JSON reports and compile statistics into a CSV file. "
                    "Supports both nested (trimmed_data/sample/sample.json) and "
                    "flat (directory/*.json) structures."
    )
    parser.add_argument(
        '-i', '--input',
        nargs='+',
        required=True,
        help='One or more paths to directories containing fastp JSON files'
    )
    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output CSV file path'
    )
    parser.add_argument(
        '--output-mqc',
        required=False,
        default=None,
        help='Optional output path for a MultiQC custom-content YAML file '
             '(adds Raw/Final Reads/Bases columns to the General Statistics table)'
    )

    args = parser.parse_args()

    # Find all fastp JSON files
    fastp_files = find_fastp_files(args.input)

    if not fastp_files:
        print("Error: No fastp JSON files found in any of the specified directories", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(fastp_files)} fastp JSON files to process", file=sys.stderr)

    # Define CSV header
    header = [
        'sample_name',
        'before_total_reads', 'before_total_bases', 'before_q20_bases', 'before_q30_bases',
        'before_q20_rate', 'before_q30_rate', 'before_gc_content',
        'after_total_reads', 'after_total_bases', 'after_q20_bases', 'after_q30_bases',
        'after_q20_rate', 'after_q30_rate', 'after_gc_content',
        'passed_filter_reads', 'low_quality_reads', 'too_many_N_reads',
        'too_short_reads', 'too_long_reads',
        'duplication_rate', 'insert_size_peak'
    ]

    mqc_data = {}

    # Process files and write CSV
    with open(args.output, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)

        processed_count = 0
        for sample_name, json_path in sorted(fastp_files):
            stats = parse_fastp_json(json_path)

            if stats is not None:
                row = [sample_name] + [stats.get(col, 'NA') for col in header[1:]]
                writer.writerow(row)
                processed_count += 1
                print(f"Processed: {sample_name}", file=sys.stderr)

                # Scaled (millions) counts for the MultiQC general stats yaml
                mqc_data[sample_name] = {
                    'raw_reads':   stats['before_total_reads'] / 1e6,
                    'raw_bases':   stats['before_total_bases'] / 1e6,
                    'final_reads': stats['after_total_reads'] / 1e6,
                    'final_bases': stats['after_total_bases'] / 1e6,
                }
            else:
                print(f"Skipped: {sample_name} (parsing failed)", file=sys.stderr)

    print(f"\nCompleted: {processed_count}/{len(fastp_files)} samples processed", file=sys.stderr)
    print(f"Output: {args.output}", file=sys.stderr)

    if args.output_mqc:
        write_general_stats_mqc(mqc_data, args.output_mqc)
        print(f"MultiQC general stats yaml: {args.output_mqc}", file=sys.stderr)


if __name__ == "__main__":
    main()
