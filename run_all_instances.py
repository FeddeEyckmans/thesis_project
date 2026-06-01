import subprocess
import os
import sys

"""
RECIFE-MILP Bulk Generation & KPI Extraction Tool
-------------------------------------------------
This script automates the generation of multiple railway instances via Flatland.
It runs the main generator script as a separate subprocess for each instance to 
ensure a clean memory state and isolated random seeds.

Furthermore, it captures the standard output (stdout) of the generator in real-time
to extract KPIs such as topological complexity and matchmaking efficiency
"""
# --- Configuration for the Batch Run ---
START_SEED = 0
END_SEED = 50  # Define the batch size (e.g., 50 or 100 instances)
MAIN_SCRIPT = "Main_generator.py"
CITIES = 6 # Target number of stations to be placed by Flatland. Needs to match the number of stations as defined in the subscript (to check whether all instances were able to place all cities on the grid.

def run_bulk_generation():
    """
    Executes the bulk generation process, parses live terminal output,
    and generates a summary report of the dataset's validity and complexity.

    Returns:
        None (Outputs a comprehensive report to the terminal).
    """
    incomplete_instances = []
    matchmaker_stats = []
    attempt_stats = []
    tds_per_instance = []
    # Initialize global configuration trackers (safeguard against early crashes)
    topology_config = "Unknown (Check generator script)"
    generator_settings = "Unknown (Check generator script)"
    print(f"--- STARTING BULK GENERATION OF {END_SEED - START_SEED} INSTANCES ---")

    for current_seed in range(START_SEED, END_SEED):
        instance_name = f"Instance_{current_seed:03d}"
        print(f"\n[MASTER] >>> Launching {instance_name} using Seed: {current_seed}...")

        # Default state. Overwritten by an integer if the matchmaking loop succeeds.
        attempts_for_this_seed = "Failed"

        # Launch the generator as an isolated subprocess
        process = subprocess.Popen(
            ["python", MAIN_SCRIPT, "--mode", "both", "--seed", str(current_seed)],
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

            if "GENERATOR_PARAMS:" in line:
                generator_settings = line.split("GENERATOR_PARAMS:")[1].strip()

            # 3. Validate city placement (Flag instances where Flatland failed to place all cities)
            if "ACTUAL_CITIES_PLACED:" in line:
                try:
                    actual_cities = int(line.split(":")[1].strip())
                    if actual_cities < CITIES:
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
            # Expected format: "MATCHMAKER_STATS: Made 13, Rejected 5"
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
            # Expected format: "... Found a perfect, conflict-free roster on attempt 2."
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
    if not incomplete_instances:
        print(f"\nCITY PLACEMENT: All instances successfully placed {CITIES} cities.")
    else:
        print(f"\nCITY PLACEMENT WARNING: Found {len(incomplete_instances)} instances with < {CITIES} cities.")
        for seed, actual_cities in incomplete_instances:
            print(f"  -> Seed {seed:03d} has only {actual_cities} cities.")

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