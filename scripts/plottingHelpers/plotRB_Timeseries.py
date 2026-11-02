import os
import glob
import pandas as pd
import matplotlib.pyplot as plt

# Configuration parameters
operator = "Airtel"
location = "indoor_Bharti501"
date = "20261013"

# Define patterns for both downlink and uplink files
input_patterns = [
    f"results/rb_combined/{operator}/{location}/{date}_rb_downlink.csv",
    f"results/rb_combined/{operator}/{location}/{date}_rb_uplink.csv"
]

output_dir = "graphs/dummyVC/rb_combined"
os.makedirs(output_dir, exist_ok=True)

# Define custom colors for RAT types (optional)
rat_colors = {'4G': 'blue', '5G': 'orange'}

# Process each file path pattern
for input_path in input_patterns:
    # Use glob to safely check/resolve paths if files exist
    matched_files = glob.glob(input_path)
    
    if not matched_files:
        print(f"File not found: {input_path}, skipping...")
        continue

    for file_path in matched_files:
        print(f"\nProcessing file: {file_path}")
        
        # Determine link type (downlink/uplink) from filename for labeling/saving
        link_type = "downlink" if "downlink" in file_path else "uplink"
        
        # Load the CSV dataset
        df = pd.read_csv(file_path)

        # Convert timestamp column to datetime format and sort chronologically
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')

        # Group by each capture file (run) and generate a plot
        for run_name, group in df.groupby('run'):
            plt.figure(figsize=(12, 6))
            
            # Loop through each RAT type (e.g., 4G, 5G) to plot them separately with Matplotlib
            for rat_type, rat_group in group.groupby('rat'):
                plt.plot(
                    rat_group['timestamp'],
                    rat_group['rb'],
                    label=str(rat_type),
                    marker='o',
                    markersize=4,
                    linewidth=1.5,
                    color=rat_colors.get(rat_type, None)  # Fallback to default if not in dict
                )
            
            plt.title(f'RB ({link_type.capitalize()}) - Operator: {operator} | Location: {location} | Run: {run_name}', fontsize=11, pad=12)
            plt.xlabel('Timestamp', fontsize=10)
            plt.ylabel('RB', fontsize=10)
            plt.xticks(rotation=30)
            plt.legend(title='RAT', loc='upper right')
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.tight_layout()
            
            # Save the plot with link type distinction in the filename
            output_file = os.path.join(output_dir, f"{date}_{operator}_{location}_{run_name}_{link_type}.png")
            plt.savefig(output_file, dpi=300)
            plt.close()
            print(f"  -> Saved plot: {output_file}")

print("\nAll available plots successfully generated!")