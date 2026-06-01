# Experimental Matrix: Reproducibility Guide

This document provides a complete mapping between the experimental design presented in the thesis and the generation commands required to reproduce every railway instance.

The experiments were designed for the sensitivity analysis described in Chapter 4. For each parameter set, the generation pipeline was executed for **50 independent random seeds (0–49)**, resulting in:

* **25 parameter configurations**
* **50 instances per configuration**
* **1,250 generated railway scenarios in total**

All experiments can be reproduced using `run_all_instances.py`.

---

# General Reproduction Settings

Unless stated otherwise, every experiment uses:

```bash
python run_all_instances.py --start_seed 0 --end_seed 50
```

which generates one instance for each seed in the range `[0,49]`.

---

# Topology A — Small Stations

**Infrastructure characteristics**

| Parameter | Value                 |
| --------- | --------------------- |
| Grid Size | 45 × 45               |
| Stations  | 6                     |
| Platforms | 4 / 2 / 2 / 2 / 2 / 2 |

This topology represents the baseline infrastructure with relatively small station capacities.

## Experimental Configurations

| ID  | Courses | Perturbation |
| --- | ------- | ------------ |
| A01 | 20      | 10%          |
| A02 | 20      | 20%          |
| A03 | 20      | 40%          |
| A04 | 40      | 10%          |
| A05 | 40      | 20%          |
| A06 | 40      | 40%          |
| A07 | 60      | 10%          |
| A08 | 60      | 20%          |
| A09 | 60      | 40%          |
| A10 | 80      | 10%          |
| A11 | 80      | 20%          |
| A12 | 80      | 40%          |
| A13 | 100     | 10%          |
| A14 | 100     | 20%          |
| A15 | 100     | 40%          |

### Commands

```bash
# A01
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 20 --perturbation 0.10

# A02
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 20 --perturbation 0.20

# A03
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 20 --perturbation 0.40

# A04
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 40 --perturbation 0.10

# A05
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 40 --perturbation 0.20

# A06
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 40 --perturbation 0.40

# A07
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 60 --perturbation 0.10

# A08
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 60 --perturbation 0.20

# A09
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 60 --perturbation 0.40

# A10
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 80 --perturbation 0.10

# A11
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 80 --perturbation 0.20

# A12
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 80 --perturbation 0.40

# A13
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 100 --perturbation 0.10

# A14
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 100 --perturbation 0.20

# A15
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 45 --stations 6 --platforms "4,2,2,2,2,2" --courses 100 --perturbation 0.40
```

---

# Topology B — Large Stations

**Infrastructure characteristics**

| Parameter | Value                 |
| --------- | --------------------- |
| Grid Size | 55 × 55               |
| Stations  | 6                     |
| Platforms | 6 / 3 / 3 / 2 / 2 / 2 |

This topology represents the enlarged infrastructure with higher station capacities.

## Experimental Configurations

| ID  | Courses | Perturbation |
| --- | ------- | ------------ |
| B01 | 20      | 10%          |
| B02 | 20      | 20%          |
| B03 | 40      | 10%          |
| B04 | 40      | 20%          |
| B05 | 60      | 10%          |
| B06 | 60      | 20%          |
| B07 | 80      | 10%          |
| B08 | 80      | 20%          |
| B09 | 100     | 10%          |
| B10 | 100     | 20%          |

### Commands

```bash
# B01
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 20 --perturbation 0.10

# B02
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 20 --perturbation 0.20

# B03
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 40 --perturbation 0.10

# B04
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 40 --perturbation 0.20

# B05
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 60 --perturbation 0.10

# B06
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 60 --perturbation 0.20

# B07
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 80 --perturbation 0.10

# B08
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 80 --perturbation 0.20

# B09
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 100 --perturbation 0.10

# B10
python run_all_instances.py --start_seed 0 --end_seed 50 --grid_size 55 --stations 6 --platforms "6,3,3,2,2,2" --courses 100 --perturbation 0.20
```

---

# Complete Dataset

The complete experimental campaign consists of:

| Category                  | Count |
| ------------------------- | ----- |
| Topologies                | 2     |
| Parameter Sets            | 25    |
| Seeds per Set             | 50    |
| Total Generated Instances | 1,250 |

Running all commands listed in this document reproduces the full dataset used for the sensitivity analysis reported in the thesis.
