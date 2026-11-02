
# -------------------------------------------------------------------- #

# Master script for compiling data and plotting graphs for analysis

# -------------------------------------------------------------------- #
# In this script, we use the QMDL Metric CSVs, Coverage metric CSVs and throughput CSVs to make required graph plots.

#  Note : Please ensure that QMDL logs have been converted to CSVs using scat.

# -------------------------------------------------------------------- #
#                           Configuration
# -------------------------------------------------------------------- #
LOCATIONS_DATES = {
    # "indoor_Bharti501": ["20261006"],
    "indoor_Bharti501": ["20261006", "20261013"],
    "indoor_AzadApt": ["20261013", "20261015"],
    "indoor_BlueTokai": ["20261012", "20261013"],
    "indoor_Shubham_JiaSarai": ["20261017", "20261018"],
    "outdoor_Car": ["20261012", "20261013"],
    "outdoor_Ground": ["20261011", "20261012"],
    "outdoor_Rajdhani": ["20261012", "20261013"],
}
RADIO_CONNECTION = ["5G", "4G"]
WINDOW_SIZE = 1000
import subprocess, sys
for day_idx in range(2):
    for loc, dates in LOCATIONS_DATES.items():
        date = dates[day_idx]  # Pulls the correct date for this location
# -------------------------------------------------------------------- #
#           Step 1 : Build Coverage Metrics
# -------------------------------------------------------------------- #

# cmd = [
#     "python", "scripts/dataCompilationScripts/build_Coverage_metrics.py",
#     "--locations", *LOCATIONS,
#     "--dates", *DATES
# ]
# result = subprocess.run(cmd, capture_output=True, text=True)
# if result.returncode == 0:
#     print("Coverage Metrics extraction completed successfully!")
#     print(result.stdout)
# else:
#     print("Error during extraction for Coverage Metrics:")
#     print(result.stderr)

# -------------------------------------------------------------------- #
#           Step 2 : Build QMDL Metrics (speedtest + dummy VC)
# -------------------------------------------------------------------- #
        # cmd = [
        #     "python", "scripts/dataCompilationScripts/build_QMDL_metrics.py",
        #     "--locations", loc,
        #     "--dates", date,
        #     "--use_speedtest",
        # ]
        # result = subprocess.run(cmd, capture_output=True, text=True)
        # if result.returncode == 0:
        #     print("QMDL Metrics CSV for speedtest completed successfully!")
        #     print(result.stdout)
        # else:
        #     print("Error during extraction for QMDL Metrics speedtest")
        #     print(result.stderr)

        # cmd = [
        #     "python", "scripts/dataCompilationScripts/build_QMDL_metrics.py",
        #     "--locations", loc,
        #     "--dates", date,
        # ]
        # result = subprocess.run(cmd, capture_output=True, text=True)
        # if result.returncode == 0:
        #     print("QMDL Metrics CSV for dummy VC completed successfully!")
        #     print(result.stdout)
        # else:
        #     print("Error during extraction for QMDL Metrics dummy VC")
        #     print(result.stderr)

# -------------------------------------------------------------------- #
#           Step 3 : Plot the fallback graphs
# -------------------------------------------------------------------- #
        # cmd = [
        #     sys.executable, "scripts/dataAnalysisScripts/fallback_analysis_with_granularity.py",
        #     "--locations", loc,
        #     "--dates", date,
        #     "--window_ms", str(WINDOW_SIZE),
        #     "--use_speedtest", str(True),       # or str(False), or str(your_variable)
        # ]
        # result = subprocess.run(cmd, capture_output=True, text=True)
        # if result.returncode == 0:
        #     print("Speedtest Fallback graphs for speedtest completed successfully!")
        #     print(result.stdout)
        # else:
        #     print("Error during extraction for Speedtest Fallback graphs")
        #     print(result.stderr)

        # cmd = [
        #     sys.executable, "scripts/dataAnalysisScripts/fallback_analysis_with_granularity.py",
        #     "--locations", loc,
        #     "--dates", date,
        #     "--window_ms", str(WINDOW_SIZE),
        #     "--use_speedtest", str(False),       # or str(False), or str(your_variable)
        # ]
        # result = subprocess.run(cmd, capture_output=True, text=True)
        # if result.returncode == 0:
        #     print("Fallback graphs for dummy VC completed successfully!")
        #     print(result.stdout)
        # else:
        #     print("Error during extraction for Fallback graphs dummy VC")
        #     print(result.stderr)

# -------------------------------------------------------------------- #
#           Step 4 : Plot the CDF for Resource Blocks
# -------------------------------------------------------------------- #

        # cmd = [
        #     sys.executable, "scripts/plottingHelpers/plotCDF.py",
        #     "--locations", loc,
        #     "--dates", date,
        #     "--use_speedtest",
        # ]
        # result = subprocess.run(cmd, capture_output=True, text=True)
        # if result.returncode == 0:
        #     print("Speedtest Resource blocks CDF plot completed successfully!")
        #     print(result.stdout)
        # else:
        #     print("Error during extraction for Speedtest Resource blocks CDF plot")
        #     print(result.stderr)

        # cmd = [
        #     sys.executable, "scripts/plottingHelpers/plotCDF.py",
        #     "--locations", loc,
        #     "--dates", date,
        # ]
        # result = subprocess.run(cmd, capture_output=True, text=True)
        # if result.returncode == 0:
        #     print("Dummy VC Resource blocks CDF plot completed successfully!")
        #     print(result.stdout)
        # else:
        #     print("Error during extraction for Dummy VC Resource blocks CDF plot")
        #     print(result.stderr)

# -------------------------------------------------------------------- #
#           Step 5 : Plot Ratio Bar plots for Coverage Metrics
# -------------------------------------------------------------------- #

# cmd = [
#     sys.executable, "scripts/plottingHelpers/generate_ratio_plots_coverage.py",
#     "--locations", *LOCATIONS,
#     "--dates", *DATES,
#     "--scenario", "speedtest"
# ]
# result = subprocess.run(cmd, capture_output=True, text=True)
# if result.returncode == 0:
#     print("Speedtest Coverage Ratio Plots completed successfully!")
#     print(result.stdout)
# else:
#     print("Error during extraction for Speedtest Coverage Ratio Plots")
#     print(result.stderr)

# cmd = [
#     sys.executable, "scripts/plottingHelpers/generate_ratio_plots_coverage.py",
#     "--locations", *LOCATIONS,
#     "--scenario", "dummyVC",
#     "--dates", *DATES,
# ]
# result = subprocess.run(cmd, capture_output=True, text=True)
# if result.returncode == 0:
#     print("Dummy VC Coverage Ratio Plots completed successfully!")
#     print(result.stdout)
# else:
#     print("Error during extraction for Dummy VC Coverage Ratio Plots")
#     print(result.stderr)

# -------------------------------------------------------------------- #
#           Step 6 : Plot Ratio Bar plots for QMDL Metrics
# -------------------------------------------------------------------- #
        # for i in range(len(RADIO_CONNECTION)):
        #     cmd = [
        #         sys.executable, "scripts/plottingHelpers/generate_ratio_plots_QMDL.py",
        #         "--locations", loc,
        #         "--dates", date,
        #         "--scenario", "speedtest",
        #         "--radio_connection", RADIO_CONNECTION[i],
        #     ]
        #     result = subprocess.run(cmd, capture_output=True, text=True)
        #     if result.returncode == 0:
        #         print("Speedtest QMDL Ratio Plots completed successfully!")
        #         print(result.stdout)
        #     else:
        #         print("Error during extraction for Speedtest QMDL Ratio Plots")
        #         print(result.stderr)

        #     cmd = [
        #         sys.executable, "scripts/plottingHelpers/generate_ratio_plots_QMDL.py",
        #         "--locations", loc,
        #         "--dates", date,
        #         "--scenario", "dummyVC",
        #         "--radio_connection", RADIO_CONNECTION[i],
        #     ]
        #     result = subprocess.run(cmd, capture_output=True, text=True)
        #     if result.returncode == 0:
        #         print("Dummy VC QMDL Ratio Plots completed successfully!")
        #         print(result.stdout)
        #     else:
        #         print("Error during extraction for Dummy VC QMDL Ratio Plots")
        #         print(result.stderr)

# -------------------------------------------------------------------- #
#                 Step 7 : Estimate B/w (for regression)
# -------------------------------------------------------------------- #
        cmd = [
            sys.executable, "scripts/dataAnalysisScripts/estimate_bw.py",
            "--location", loc,
            "--dates", date,
            "--use_speedtest", "true",
            "--window_size", "1",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("Estimated Throughput for speedtest completed successfully!")
            print(result.stdout)
        else:
            print("Error during extraction for throughput estimation for speedtest")
            print(result.stderr)

        cmd = [
            sys.executable, "scripts/dataAnalysisScripts/estimate_bw.py",
            "--location", loc,
            "--dates", date,
            "--use_speedtest", "false",
            "--window_size", "1",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("Estimated Throughput for dummy VC completed successfully!")
            print(result.stdout)
        else:
            print("Error during extraction for throughput estimation for dummy VC")
            print(result.stderr)
