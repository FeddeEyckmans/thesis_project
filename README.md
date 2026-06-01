# 🚂 RECIFE-MILP Railway Scenario Generator

This pipeline converts abstract, grid-based **Flatland** railway networks into detailed microscopic XML files natively compatible with the **RECIFE-MILP** optimization engine.

---

## 📁 Repository Map

```text
thesis_project/
├── Main_generator.py                    # Generates 1 specific scenario (A* routing, signaling, XML export)
├── run_all_instances.py                 # Master script for bulk generation (e.g., running 50 seeds automatically)
├── custom_rail_generator.py             # Customized Flatland extension for custom station & platform sizes
├── custom_line_generator.py             # Customized Flatland extension for custom origin/destination platforms
├── timetable_generator_functions.py     # Functions to create the timetable XML file
└── perturbation_generator_functions.py  # Functions to create the perturbation XML file
```

---

## 🚀 Quick Start Guide

You can control all parameters directly from your terminal. If you don't provide any flags, the scripts automatically fall back to the hardcoded variables inside the code.

### 1. Generate a Single Scenario (`Main_generator.py`)

To test or visualize one specific network template, run:

```bash
python Main_generator.py --seed 101 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 40 --perturbation 0.20 --mode both
```

Add `--visualize` at the very end if you want to open the graphical Flatland map window.

### 2. Generate a 50-Instance Batch (`run_all_instances.py`)

To generate a massive dataset for your thesis tables, use the master bulk tool.

#### Option A: Run a batch using the script's default settings (Seeds 0 to 49)

```bash
python run_all_instances.py --start_seed 0 --end_seed 50
```

#### Option B: Force a specific high-density experiment across all 50 runs

```bash
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 80 --perturbation 0.40
```

> **Note:** At the end of the batch run, the tool will automatically print a KPI Summary Report in your terminal with route lengths, matchmaking efficiency, and algorithmic convergence speeds.

---

## 🔍 CLI Flag Reference

| Flag | Description |
|--------|-------------|
| `--seed [int]` | Random seed for reproducibility |
| `--start_seed [int]` | Start seed for batch generation (master script only) |
| `--end_seed [int]` | End seed for batch generation (master script only) |
| `--grid_size [int]` | Size of the square grid matrix (e.g., 45 for a 45×45 tracking grid) |
| `--stations [int]` | Total number of scheduled stations to place on the map |
| `--platforms [string]` | Platform tracks per station, separated by commas (e.g., `"6,3,3,2,2,2"`) |
| `--courses [int]` | Traffic volume (target number of validated trains in the final timetable) |
| `--perturbation [float]` | Fraction of trains that get an entrance delay (e.g., `0.20 = 20%`) |
| `--mode [both \| infra \| timetable]` | Generation mode |

### Generation Modes

#### `both`
Complete lifecycle pipeline generation.

#### `infra`
Infrastructure XML layer only.

#### `timetable`
Skip pathfinding, load track geometry from cache, and rebuild a fresh timetable instantly.

---

## 💾 Output Location

Every successful generation creates a seed-synchronized directory (automatically ignored by Git to avoid bloating your repository):

```text
Instance_042/
└── inputData/
    ├── real_infrastructure.xml  # Microscopic topology maps, signals, and blocks
    ├── real_TimeTable.xml       # Capacity-checked, conflict-free commercial timetables
    ├── real_Perturbation.xml    # Stochastic delay profiles for stress-testing
    └── infra_cache.pkl          # Cached pathfinding edge tensors
```

## Reproducibility

The complete sensitivity-analysis experiment matrix is documented in
[`experiments_matrix.md`](experiments_matrix.md).

This file contains all 25 parameter configurations and the exact commands
required to reproduce the 1,250 railway instances used in the thesis.