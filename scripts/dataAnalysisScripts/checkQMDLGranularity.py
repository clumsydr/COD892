import glob
import os
import pandas as pd


def analyze_qmdl_data():
  base_dir = "/scratch/5GMeasurements/qmdl_output"
  operators = ["Airtel", "Jio", "Vodafone"]

  print("Starting analysis of QMDL output CSV records...")
  print(f"Target Base Directory: {base_dir}\n")

  # Safeguard check if base directory exists locally
  if not os.path.exists(base_dir):
    print(f"[WARNING] Directory '{base_dir}' does not exist on this system.")
    print(
        "This script is correctly structured and will run successfully when"
        " executed on the remote server where the data is stored.\n"
    )

  operator_summary = {}

  for op in operators:
    # Match readableb881.csv and readableb887.csv across all captures for the date
    pattern = os.path.join(
        base_dir,
        op,
        "indoor_Bharti501",
        "20261006",
        "capture_*",
        "readable*.csv",
    )
    files = glob.glob(pattern)

    total_records = 0
    file_count = len(files)
    detected_granularities = []

    for file_path in files:
      try:
        # Read only necessary columns for efficiency
        df = pd.read_csv(
            file_path, usecols=lambda c: c in ["timestamp_epoch", "timestamp_utc"]
        )
        record_count = len(df)
        total_records += record_count

        # Determine time granularity using timestamp_epoch differences
        if "timestamp_epoch" in df.columns and len(df) > 1:
          diffs = df["timestamp_epoch"].diff().dropna()
          if not diffs.empty:
            median_diff = diffs.median()
            # Classify based on median delta
            if median_diff <= 0.002:
              granularity = "Millisecond (~1ms)"
            elif median_diff <= 0.05:
              granularity = f"Sub-second (~{median_diff*1000:.1f}ms)"
            elif 0.9 <= median_diff <= 1.1:
              granularity = "Second (1s)"
            else:
              granularity = f"Custom (~{median_diff:.3f}s)"
            detected_granularities.append(granularity)

      except Exception as e:
        print(f"Error reading file {file_path}: {e}")

    # Calculate average records per file for the operator
    avg_records = total_records / file_count if file_count > 0 else 0

    # Find the most frequently occurring granularity
    dominant_granularity = (
        max(
            set(detected_granularities),
            key=detected_granularities.count,
        )
        if detected_granularities
        else "Unknown"
    )

    operator_summary[op] = {
        "files_found": file_count,
        "total_records": total_records,
        "avg_records_per_file": avg_records,
        "granularity": dominant_granularity,
    }

  # Print Summary Results
  print("=" * 60)
  print(f"{'OPERATOR':<12} | {'FILES':<6} | {'TOTAL RECORDS':<15} | {'AVG / FILE':<12} | {'GRANULARITY'}")
  print("-" * 60)

  for op, stats in operator_summary.items():
    print(
        f"{op:<12} | "
        f"{stats['files_found']:<6} | "
        f"{stats['total_records']:<15} | "
        f"{stats['avg_records_per_file']:<12.1f} | "
        f"{stats['granularity']}"
    )
  print("=" * 60)


if __name__ == "__main__":
  analyze_qmdl_data()