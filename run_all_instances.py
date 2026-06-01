import subprocess
import os
import sys
import argparse

"""
RECIFE-MILP Bulk Generation & KPI Extraction Tool
-------------------------------------------------
This script automates the generation of multiple railway instances via Flatland.
It runs the main generator script as a separate subprocess for each instance to 
ensure a clean memory state and isolated random seeds.

Furthermore, it captures the standard output (stdout) of the generator in real-time
to extract KPIs such as topological complexity and matchmaking efficiency
"""


def run_bulk_generation():
    """
    Executes the bulk generation process, parses live terminal output,
    and generates a summary report of the dataset's validity and complexity.

    Returns:
        None (Outputs a comprehensive report to the terminal).
    """
    # --- 1. SET UP COMMAND LINE ARGUMENTS WITH NONE DEFAULTS ---
    parser = argparse.ArgumentParser(description="RECIFE-MILP Bulk Generation and KPI Extraction Master Tool")

    # Batch run boundaries (Defaults to None to allow hardcoded fallback)
    parser.add_argument("--start_seed", type=int, default=None, help="Starting seed index for the loop")
    parser.add_argument("--end_seed", type=int, default=None, help="Ending seed index (defines batch size)")

    # Scenario variables (Defaults set to None to let Main_generator.py dictate defaults)
    parser.add_argument("--grid_size", type=int, default=None, help="Grid size dimension")
    parser.add_argument("--stations", type=int, default=None, help="Total number of stations to place")
    parser.add_argument("--platforms", type=str, default=None, help="Platform layout configuration")
    parser.add_argument("--courses", type=int, default=None, help="Target traffic volume")
    parser.add_argument("--perturbation", type=float, default=None, help="Injected perturbation fraction")

    args = parser.parse_args()

    # =========================================================================
    # EDITABLE HARDCODED CONFIGURATION PARAMETERS (Fallback when no arguments given)
    # =========================================================================
    START_SEED = 0
    END_SEED = 50
    # =========================================================================

    # --- Overwrite fallback defaults for seed loop if provided via terminal ---
    if args.start_seed is not None:
        START_SEED = args.start_seed
    if args.end_seed is not None:
        END_SEED = args.end_seed

    MAIN_SCRIPT = "Main_generator.py"

    # We gebruiken deze variabele tijdelijk voor het eindrapport; als --stations niet is
    # meegegeven, weten we het pas zeker zodra Main_generator de PARAM_REPORT print.
    expected_cities = args.stations if args.stations is not None else "Dynamic (Main Generator Default)"

    incomplete_instances = []
    matchmaker_stats = []
    attempt_stats = []
    tds_per_instance = []

    # Initialize global configuration trackers (safeguard against early crashes)
    topology_config = "Unknown (Check generator script)"
    generator_settings = "Unknown (Check generator script)"

    print(f"=========================================================================")
    print(f"   STARTING MASTER BULK GENERATION OF {END_SEED - START_SEED} INSTANCES  ")
    print(f"=========================================================================")
    print(f"Loop Configuration:")
    print(f"Seeds        : From {START_SEED} to {END_SEED - 1}")
    print(f"Scenario     : Fallback to Main_generator.py defaults for unprovided flags.")
    print(f"-------------------------------------------------------------------------")

    for current_seed in range(START_SEED, END_SEED):
        instance_name = f"Instance_{current_seed:03d}"
        print(f"\n[MASTER] >>> Launching {instance_name} using Seed: {current_seed}...")

        # Default state. Overwritten by an integer if the matchmaking loop succeeds.
        attempts_for_this_seed = "Failed"

        # --- 2. CONSTRUCT THE DYNAMIC COMMAND STRING ---
        # We starten altijd met de basisvlaggen die dit script sowieso moet meegeven
        cmd = ["python", MAIN_SCRIPT, "--mode", "both", "--seed", str(current_seed)]

        # Nu voegen we de andere argumenten ALLEEN toe als ze daadwerkelijk in de terminal zijn getypt
        if args.grid_size is not None:
            cmd.extend(["--grid_size", str(args.grid_size)])
        if args.stations is not None:
            cmd.extend(["--stations", str(args.stations)])
        if args.platforms is not None:
            cmd.extend(["--platforms", args.platforms])
        if args.courses is not None:
            cmd.extend(["--courses", str(args.courses)])
        if args.perturbation is not None:
            cmd.extend(["--perturbation", str(args.perturbation)])

        # Launch the generator as an isolated subprocess passing down the filtered command array
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Parse the output line by line in real-time
        for line in process.stdout:
            # 1. Echo the line immediately to the terminal to monitor progress
            sys.stdout.write(line)
            sys.stdout.flush()

            # 2. Extract global topology variables (reported by the main script)
            if "PARAM_REPORT:" in line:
                topology_config = line.split("PARAM_REPORT:")[1].strip()
                # Dynamisch de verwachte steden oppikken uit de report als we het niet wisten
                if isinstance(expected_cities, str) and "Cities=" in topology_config:
                    try:
                        expected_cities = int(topology_config.split("Cities=")[1].split(",")[0].strip())
                    except:
                        pass

            if "GENERATOR_PARAMS:" in line:
                generator_settings = line.split("GENERATOR_PARAMS:")[1].strip()

            # 3. Validate city placement (Flag instances where Flatland failed to place all cities)
            if "ACTUAL_CITIES_PLACED:" in line:
                try:
                    actual_cities = int(line.split(":")[1].strip())
                    if isinstance(expected_cities, int) and actual_cities < expected_cities:
                        incomplete_instances.append((current_seed, actual_cities))
                except (ValueError, IndexError):
                    pass

            # 4. Extract Average Track Detection Section (TDS) metrics
            if "AVG_TDS_REPORT:" in line:
                try:
                    avg_tds = float(line.split(":")[1].strip())
                    tds_per_instance.append({'seed': current_seed, 'avg': avg_tds})
                except (ValueError, IndexError):
                    pass

            # 5. Extract Rolling Stock Matchmaker statistics
            if "MATCHMAKER_STATS:" in line:
                try:
                    parts = line.split(":")[1].split(",")
                    made_this_run = int(parts[0].strip().split(" ")[1])
                    rejected_this_run = int(parts[1].strip().split(" ")[1])
                    matchmaker_stats.append({
                        'seed': current_seed,
                        'made': made_this_run,
                        'rejected': rejected_this_run
                    })
                except (ValueError, IndexError):
                    pass

            # 6. Extract Iterative Roster Building performance
            if "[SUCCESS] Iterative process complete! Found a (spatial) conflict-free roster on attempt" in line:
                try:
                    attempts_str = line.split("attempt ")[1].split(".")[0].strip()
                    attempts_for_this_seed = int(attempts_str)
                except (ValueError, IndexError):
                    pass

        # Wait for the subprocess to terminate fully before moving to the next seed
        process.wait()

        # Log the attempts required for this specific instance
        attempt_stats.append({
            'seed': current_seed,
            'attempts': attempts_for_this_seed
        })

        if process.returncode == 0:
            print(f"[MASTER] Successfully completed {instance_name}.")
        else:
            print(f"[ERROR] {instance_name} crashed with exit code {process.returncode}.")

    # ==========================================
    # FINAL SUMMARY REPORT GENERATION
    # ==========================================
    print("\n" + "=" * 70)
    print(f"{'FINAL BATCH RUN SUMMARY':^70}")
    print("=" * 70)

    # Part 1: Global Configurations
    print("\nGLOBAL EXPERIMENT CONFIGURATION:")
    print(f"Topology:  {topology_config}")
    print(f"Generator: {generator_settings}")
    print("-" * 80)

    # Part 2: Network Complexity (TDS Count)
    print("\nROUTE LENGTH ANALYSIS (TDS per Journey):")
    print(f"{'Seed':<10} | {'Average TDS Count'}")
    print("-" * 40)

    total_tds_sum = 0
    for stat in tds_per_instance:
        print(f"Seed {stat['seed']:03d}  | {stat['avg']:.2f} TDS")
        total_tds_sum += stat['avg']

    print("-" * 40)
    if tds_per_instance:
        grand_avg_tds = total_tds_sum / len(tds_per_instance)
        print(f"OVERALL AVG| {grand_avg_tds:.2f} TDS per journey")
    else:
        print("OVERALL AVG| No data collected")

    # Part 3: Validity Check (City Placement)
    if isinstance(expected_cities, int):
        if not incomplete_instances:
            print(f"\nCITY PLACEMENT: All instances successfully placed {expected_cities} cities.")
        else:
            print(
                f"\nCITY PLACEMENT WARNING: Found {len(incomplete_instances)} instances with < {expected_cities} cities.")
            for seed, actual_cities in incomplete_instances:
                print(f"  -> Seed {seed:03d} has only {actual_cities} cities.")
    else:
        print(f"\nCITY PLACEMENT: Could not verify constraint bounds (dynamic network topology).")

    # Part 4: Algorithmic Convergence (Attempts)
    print("\nITERATIVE MATCHMAKING ATTEMPTS:")
    print(f"{'Seed':<10} | {'Attempts Needed'}")
    print("-" * 60)

    total_attempts = 0
    success_count = 0

    for stat in attempt_stats:
        seed = stat['seed']
        attempts = stat['attempts']
        print(f"Seed {seed:03d}  | {attempts}")

        if isinstance(attempts, int):
            total_attempts += attempts
            success_count += 1

    print("-" * 60)
    if success_count > 0:
        avg_attempts = total_attempts / success_count
        print(f"AVERAGE    | {avg_attempts:.2f} attempts per successful instance")
        failed_count = (END_SEED - START_SEED) - success_count
        print(f"FAILED     | {failed_count} instances ran out of reserve trains")
    else:
        print("FAILED     | All instances failed to generate a valid roster.")

    # Part 5: Rolling Stock Efficiency
    print("\nROLLING STOCK CONNECTION ANALYSIS:")
    print(f"{'Seed':<10} | {'Made':<10} | {'Rejected':<10} | {'Efficiency'}")
    print("-" * 60)

    total_made = 0
    total_rejected = 0

    for stat in matchmaker_stats:
        total = stat['made'] + stat['rejected']
        efficiency = (stat['made'] / total * 100) if total > 0 else 0
        print(f"Seed {stat['seed']:03d}  | {stat['made']:<10} | {stat['rejected']:<10} | {efficiency:.1f}%")
        total_made += stat['made']
        total_rejected += stat['rejected']

    print("-" * 60)
    grand_total = total_made + total_rejected
    if grand_total > 0:
        overall_efficiency = (total_made / grand_total * 100)
        print(f"OVERALL    | {total_made:<10} | {total_rejected:<10} | {overall_efficiency:.1f}%")
    else:
        print(f"OVERALL    | No rolling stock data collected.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_bulk_generation()