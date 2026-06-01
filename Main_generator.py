"""
RECIFE-MILP Data Generation Pipeline via Flatland
-------------------------------------------------
This script generates a railway infrastructure and timetable using the
Flatland environment and exports it to XML format compatible with RECIFE-MILP.
It handles track layout generation, signal placement, journey routing (A*),
and automated conflict-free timetable pre-processing.
"""
# --- Standard Library Imports ---
import argparse
import copy
import itertools
import heapq
import os
import pickle
from types import SimpleNamespace
import random

# --- Third-Party Imports ---
import lxml.etree as ET
import matplotlib.pyplot as plt
import numpy as np

# --- Flatland Imports ---
from flatland.envs.rail_env import RailEnv
from flatland.utils.rendertools import RenderTool
from flatland.core.grid.grid4_utils import get_new_position
from flatland.envs.rail_env_shortest_paths import DistanceMap

# --- Flatland Extensions & RECIFE Connectors ---
from flatland_railway_extension.FlatlandEnvironmentHelper import FlatlandEnvironmentHelper

# --- Custom Module Imports ---
from timetable_generator_functions import (
    generate_timetable_xml,
    generate_coursetypes_xml,
    save_timetable_xml,
    generate_courses_xml,
    calculate_rolling_stock_connections,
    generate_connections_xml,
    filter_directional_conflicts
)
from perturbation_generator_functions import generate_random_scenario

def generate_full_tds_xml(env, infra_def, platforms_list):
    """
    Generates the TrackDetectionSection (TDS) entries for every active cell
    in the Flatland grid and appends them to the RECIFE XML infrastructure definition.

    In RECIFE, a TDS represents a physical block of track. Since Flatland allows
    multiple paths (transitions) through a single cell (e.g., a switch or crossing),
    each valid transition is modeled as a 'TopologyPart' and wrapped in a
    'TopologySequence' within the TDS container.

    Args:
        env (RailEnv): The generated Flatland environment.
        infra_def (xml.etree.ElementTree.Element): The XML root for InfrastructureDefinition.
        platforms_list (list): A list of tuples containing ((row, col), platform_id).

    Returns:
        xml.etree.ElementTree.Element: The root XML element containing the completed infrastructure objects.
    """
    # 16-bit transition array used by Flatland to map incoming to outgoing orientation bits.
    # Cardinal directions: N=North, E=East, S=South, W=West.
    TRANSITION_NAMES = [
        "NN", "NE", "NS", "NW",
        "EN", "EE", "ES", "EW",
        "SN", "SE", "SS", "SW",
        "WN", "WE", "WS", "WW"
    ]

    # Constants required for RECIFE validation structure.
    # Note: Explicit speed and radius values do not affect optimization outcomes here,
    # as macro running times are directly injected during timetable generation.
    CELL_SIZE = 500
    SPEED_STRAIGHT = "160"
    SPEED_CURVE = "160"
    RADIUS_STRAIGHT = "0"
    RADIUS_CURVE = "0"
    STRAIGHT_TRANSITIONS = ["NN", "SS", "EE", "WW"]

    # Invert directions to establish the physical entrance side of a grid boundary.
    # For example, a train heading North ('N') enters the cell from the South boundary ('S').
    INVERSE_DIR = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}

    #NO FURTEHER RELEVANCE
    # Anchor positions mapped inside a schematic 100x100 cell box.
    # Provided to maintain architectural compatibility with the RECIFE XML visual layout requirements.
    VIS_ANCHORS = {
        'N': {'x': 50.0, 'y': 0.0},
        'E': {'x': 100.0, 'y': 50.0},
        'S': {'x': 50.0, 'y': 100.0},
        'W': {'x': 0.0, 'y': 50.0}
    }

    # Initialize the main Track Detection Sections container
    tcs_container = ET.SubElement(infra_def, "trackDetectionSections")

    # Convert platform structures to a set of coordinates for efficient O(1) lookups
    platform_coords = {pos for pos, _ in platforms_list}

    # Extract environmental dimensions
    height, width = env.rail.grid.shape

    # Process layout block-by-block across the structural grid matrix
    for r in range(height):
        for c in range(width):

            #16 bit string coding for all possible entry/exit combinations. 1 --> valid transition
            cell_transition = env.rail.get_full_transitions(r, c)

            # Execution pathway triggered only if the cell contains physical rail tracks
            if cell_transition > 0:

                # --- 1. Base TDS Container Generation ---
                tds_id = f"TDS_{r}_{c}"
                tds = ET.SubElement(tcs_container, "trackDetectionSection", TDS_Id=tds_id)
                ET.SubElement(tds, "name").text = tds_id

                topo_parts = ET.SubElement(tds, "topologyParts")

                # Scale local coordinates to the global map matrix layout
                base_x = c * CELL_SIZE
                base_y = r * CELL_SIZE

                # --- 2. TopologyParts Generation ---
                # Evaluate all 16 register configuration bits to locate valid track pathways
                for i in range(16):
                    # Perform bitwise extraction to confirm if a specific directional orientation is active
                    if (cell_transition >> (15 - i)) & 1:
                        trans_name = TRANSITION_NAMES[i]
                        entry_dir = trans_name[0]  # Heading orientation on layout entry
                        exit_dir = trans_name[1]  # Heading orientation on layout exit

                        entry_side = INVERSE_DIR[entry_dir]
                        exit_side = exit_dir

                        part_id = f"part_{r}_{c}_{trans_name}"

                        # A. Instantiate the primitive track segment
                        tp = ET.SubElement(topo_parts, "topologyPart", topoPart_Id=part_id)
                        ET.SubElement(tp, "length").text = str(CELL_SIZE)

                        #Speed, curve and visualisation has no further relevance and does not influence RECIFE's performance (just placeholders to match the XML-format)
                        # B. Populate speed policies and profile limits
                        if trans_name in STRAIGHT_TRANSITIONS:
                            speed = SPEED_STRAIGHT
                            curve_val = RADIUS_STRAIGHT
                        else:
                            speed = SPEED_CURVE
                            curve_val = RADIUS_CURVE

                        ET.SubElement(tp, "speednormal").text = speed
                        ET.SubElement(tp, "speedinverse").text = speed
                        ET.SubElement(tp, "gradient").text = "0"
                        ET.SubElement(tp, "curve").text = curve_val

                        # C. Build visual vector coordinates for schema representation
                        vis = ET.SubElement(tp, "visualization")
                        start_pt = VIS_ANCHORS[entry_side]
                        end_pt = VIS_ANCHORS[exit_side]

                        ET.SubElement(vis, "start",
                                      x=str(int(base_x + start_pt['x'])),
                                      y=str(int(base_y + start_pt['y'])))
                        ET.SubElement(vis, "end",
                                      x=str(int(base_x + end_pt['x'])),
                                      y=str(int(base_y + end_pt['y'])))

                # --- 3. Virtual Platform Part Generation ---
                # RECIFE requires stopping locations to reference an internal node of length 0
                if (r, c) in platform_coords:
                    v_part_id = f"vTopoPart_TDS_{r}_{c}"
                    v_tp = ET.SubElement(topo_parts, "topologyPart", topoPart_Id=v_part_id)
                    ET.SubElement(v_tp, "length").text = "0"
                    ET.SubElement(v_tp, "speednormal").text = "999"
                    ET.SubElement(v_tp, "speedinverse").text = "999"
                    ET.SubElement(v_tp, "gradient").text = "0"
                    ET.SubElement(v_tp, "curve").text = "0"

                    v_vis = ET.SubElement(v_tp, "visualization")
                    ET.SubElement(v_vis, "start", x="0", y="0")
                    ET.SubElement(v_vis, "end", x="0", y="0")

                # --- 4. TopologySequences Generation ---
                # In this single-cell interlocking mapping, each track option operates as a separate sequence
                topo_sequences = ET.SubElement(tds, "topologySequences")
                for i in range(16):
                    if (cell_transition >> (15 - i)) & 1:
                        trans_name = TRANSITION_NAMES[i]
                        part_id = f"part_{r}_{c}_{trans_name}"
                        seq_id = f"seq_{r}_{c}_{trans_name}"

                        ts = ET.SubElement(topo_sequences, "topologySequence", topoSeq_Id=seq_id)
                        tp_list = ET.SubElement(ts, "topoPart_List")

                        # direction="1" signifies progressive forward movement along the tracking vector
                        tp_elmt = ET.SubElement(tp_list, "topoPartSeqElmt", index="0")
                        ref = ET.SubElement(tp_elmt, "topoPart_RefId", direction="1")
                        ref.text = part_id

                # Append logical sequence definitions for station platforms where applicable
                if (r, c) in platform_coords:
                    v_part_id = f"vTopoPart_TDS_{r}_{c}"
                    v_seq_id = f"vTopoSeq_TDS_{r}_{c}"

                    ts = ET.SubElement(topo_sequences, "topologySequence", topoSeq_Id=v_seq_id)
                    tp_list = ET.SubElement(ts, "topoPart_List")

                    tp_elmt = ET.SubElement(tp_list, "topoPartSeqElmt", index="0")
                    ref = ET.SubElement(tp_elmt, "topoPart_RefId", direction="1")
                    ref.text = v_part_id

    return None


def generate_signals_xml(infra_def_element, env):
    """
    Generates and places physical signals at the exit boundary of every active grid cell
    for each valid outgoing direction, establishing a brick-wall block layout.

    In this specific RECIFE implementation, the architectural paradigm follows:
    1 TrackDetectionSection (TDS) = 1 Interlocking Block Section = 1 Grid Cell.
    Therefore, physical signaling devices must guard the exit boundary lines of every cell
    to regulate block occupancy transitions cleanly.

    Args:
        infra_def_element (xml.etree.ElementTree.Element): The XML root for InfrastructureDefinition.
        env (RailEnv): The generated Flatland environment.

    Returns:
        dict: A lookup table mapping (row, col, direction_out) to the generated physical signal ID.
    """
    signals_lookup = {}

    # Initialize the main XML container for all infrastructure signals
    signals_container = ET.SubElement(infra_def_element, "signals")

    # Flatland orientation index mapping: 0=North, 1=East, 2=South, 3=West
    DIR_NAMES = ["N", "E", "S", "W"]

    # Traverse the global coordinate grid layout row-by-row, column-by-column
    for r in range(env.height):
        for c in range(env.width):

            # --- 1. Filter Inactive Infrastructure ---
            cell_transitions = env.rail.get_full_transitions(r, c)
            if cell_transitions == 0:
                continue

            # --- 2. Evaluate Cell Penetration Vectors ---
            # Loop through all 4 possible entry directions to evaluate valid traversing tracks
            for d_in in range(4):
                transitions = env.rail.get_transitions(((r, c), d_in))

                # --- 3. Evaluate Outgoing Block Boundaries ---
                # Verify which outgoing direction options are physically supported by the track structure
                for d_out in range(4):
                    if transitions[d_out]:
                        # A valid trajectory exits this cell boundary heading towards 'd_out'
                        dir_name = DIR_NAMES[d_out]

                        # Define a unique identifier for the signal located at the exit side of this cell
                        sig_id = f"SIG_{r}_{c}_{dir_name}"

                        # Prevent duplicating signal instances at identical cell exit slots
                        # (e.g., when two separate internal paths converge onto the same outgoing track)
                        if (r, c, d_out) not in signals_lookup:
                            signal = ET.SubElement(signals_container, "signal", signal_Id=sig_id)
                            ET.SubElement(signal, "name").text = sig_id

                            # Hardcode to a standard 3-aspect configuration (Red/Yellow/Green) for RECIFE parser stability
                            ET.SubElement(signal, "aspects").text = "3"

                            # Populate lookup mapping dictionary used for downstream block and route parsing
                            signals_lookup[(r, c, d_out)] = sig_id

    # --- 4. Virtual Signaling Node Generation ---
    # Append a master virtual signal ('vSig') required by the RECIFE solver to manage
    # train spawning vectors from virtual zero-length platform topologies into the active grid.
    v_signal = ET.SubElement(signals_container, "signal", signal_Id="vSig")
    ET.SubElement(v_signal, "name").text = "vSig"
    ET.SubElement(v_signal, "aspects").text = "3"

    print(f"--- [SUCCESS] Generated {len(signals_lookup)} physical signals (1 per active cell exit) ---")
    return signals_lookup

def generate_blocks_xml(infra_def_element, env, signals_lookup, platform_list):
    """
    Generates the interlocking block sections for the railway infrastructure.

    This implementation strictly follows a '1-cell-per-block' paradigm.
    Each physical block connects the entry signal of a specific cell to the
    exit signal of that same cell. Additionally, it generates virtual blocks
    required for trains spawning at platform locations to enter the grid.

    Args:
        infra_def_element (xml.etree.ElementTree.Element): The XML root for InfrastructureDefinition.
        env (RailEnv): The Flatland environment.
        signals_lookup (dict): Dictionary mapping (row, col, direction_out) to a Signal ID.
        platform_list (list): A list of tuples containing ((row, col), platform_id).

    Returns:
        None (Modifies the infra_def_element XML tree in-place).
    """
    print("\n" + "=" * 60)
    print("--- Generating Interlocking Blocks (1-Cell-Per-Block) ---")

    blocks_container = ET.SubElement(infra_def_element, "blocks")
    block_counter = 0

    # Flatland directional mapping: 0=North, 1=East, 2=South, 3=West
    DIR_NAMES = ["N", "E", "S", "W"]

    # --- 1. Generate Physical Interlocking Blocks ---
    # Iterate over all placed signals.
    # (r, c, d_out) represents the location and outgoing direction of the block's entry signal.
    for (r, c, d_out), entry_sig_id in signals_lookup.items():

        # Find the adjacent cell (next_pos) guarded by this entry signal
        next_pos = get_new_position((r, c), d_out)

        if next_pos:
            nr, nc = next_pos

            # Determine possible transitions within the adjacent cell.
            # The train's entry direction (d_in) for the next cell matches exactly the
            # exit direction (d_out) of the current cell.
            next_transitions = env.rail.get_transitions((next_pos, d_out))

            for next_d_out in range(4):
                if next_transitions[next_d_out]:
                    # A valid path through the next cell is found.
                    # The exit signal for this block is located at the exit boundary of that next cell.
                    if (nr, nc, next_d_out) in signals_lookup:
                        exit_sig_id = signals_lookup[(nr, nc, next_d_out)]
                        block_id = f"BLOCK_{entry_sig_id}_TO_{exit_sig_id}"

                        # Build the XML Block Element
                        block_element = ET.SubElement(blocks_container, "block", block_Id=block_id)
                        ET.SubElement(block_element, "name").text = block_id
                        ET.SubElement(block_element, "entrySignal_RefId").text = entry_sig_id
                        ET.SubElement(block_element, "exitSignal_RefId").text = exit_sig_id

                        # Interlocking timing parameters (configured in seconds)
                        ET.SubElement(block_element, "formationTime").text = "15"
                        ET.SubElement(block_element, "releaseTime").text = "5"

                        # TDS Topology: Define the physical track sections covered by this block.
                        # In the single-cell framework model, this contains only the target cell.
                        topo_list = ET.SubElement(block_element, "TDS_Topology_List")
                        topo = ET.SubElement(topo_list, "TDS_Topology", index="0")
                        ET.SubElement(topo, "TDS_RefId").text = f"TDS_{nr}_{nc}"

                        # Link to the specific topology sequence (transition path) in that cell
                        trans_name = f"{DIR_NAMES[d_out]}{DIR_NAMES[next_d_out]}"
                        ET.SubElement(topo, "topoSeq_RefId").text = f"seq_{nr}_{nc}_{trans_name}"

                        block_counter += 1

    # --- 2. Generate Virtual Blocks for Platforms ---
    # RECIFE requires trains spawning at a platform to "enter" the network topology via a virtual block
    for (r, c), platform_id in platform_list:

        # Check all 4 outgoing directions. If a signal exists, generate a corresponding virtual block.
        for d_out in range(4):
            sig_id = signals_lookup.get((r, c, d_out))
            if sig_id:
                # Naming convention must strictly match references used during Journey Generation
                v_block_id = f"VIRTUAL_BLOCK_TO_{sig_id}"

                v_block = ET.SubElement(blocks_container, "block", block_Id=v_block_id)
                ET.SubElement(v_block, "name").text = v_block_id

                # 'vSig' represents the globally predefined virtual entry signaling node
                ET.SubElement(v_block, "entrySignal_RefId").text = "vSig"
                ET.SubElement(v_block, "exitSignal_RefId").text = sig_id

                # Virtual spawning blocks form instantly upon initialization
                ET.SubElement(v_block, "formationTime").text = "0"
                ET.SubElement(v_block, "releaseTime").text = "5"

                # TDS Topology for the virtual block maps directly to the platform cell boundaries
                topo_list = ET.SubElement(v_block, "TDS_Topology_List")
                topo = ET.SubElement(topo_list, "TDS_Topology", index="0")
                ET.SubElement(topo, "TDS_RefId").text = f"TDS_{r}_{c}"

                # Link to the internal virtual sequence structure reference
                ET.SubElement(topo, "topoSeq_RefId").text = f"vTopoSeq_TDS_{r}_{c}"

                block_counter += 1

    print(f"COMPLETE: {block_counter} blocks generated (1 cell per block).")
    print("=" * 60 + "\n")


def generate_stopping_points_xml(infra_def_element, env, signals_lookup):
    """
    Extracts train station platform data from the Flatland environment and generates
    corresponding 'stoppingPoint' XML nodes for RECIFE.

    This function maps procedural platform layouts to their respective Track
    Detection Sections (TDS) and performs a look-ahead spatial search to discover
    and link the exit signals regulating train departures from each platform.

    Args:
        infra_def_element (xml.etree.ElementTree.Element): The XML root for InfrastructureDefinition.
        env (RailEnv): The Flatland environment containing 'agents_hints'.
        signals_lookup (dict): Dictionary mapping (row, col, direction_out) to a Signal ID.

    Returns:
        list: A list of tuples containing platform coordinates and their generated unique IDs:
              [((row, col), sp_id), ...].
    """
    extracted_platforms = []

    print("\n" + "=" * 75)
    print(f"{'--- Generating Stopping Points (Platforms) ---':^75}")
    print("=" * 75)

    # Safely retrieve procedural station generation hints from the environment layout
    hints = getattr(env, 'agents_hints', None)
    if not hints or 'train_stations' not in hints:
        print("[WARNING] No station data found in Flatland hints. Skipping stopping points.")
        return extracted_platforms

    # Initialize the main XML container for stopping points
    stopping_points_container = ET.SubElement(infra_def_element, "stoppingPoints")
    train_stations = hints['train_stations']
    sp_count = 0

    # Format output tracking header for pipeline generation logging
    print(f"{'SP ID':<20} | {'Location':<10} | {'Track':<6} | {'Linked Signals'}")
    print("-" * 75)

    # Iterate through the multi-dimensional structure of cities and their internal platforms
    for city_idx, platforms in enumerate(train_stations):
        for p_idx, (pos, track_nbr) in enumerate(platforms):
            r, c = pos
            sp_id = f"SP_C{city_idx}_P{p_idx}_{r}_{c}"
            tds_ref = f"TDS_{r}_{c}"

            # Cache platform data for downstream operational journey mapping
            extracted_platforms.append((pos, sp_id))

            # --- 1. Populate Core XML Platform Nodes ---
            sp = ET.SubElement(stopping_points_container, "stoppingPoint", stoPo_Id=sp_id)
            ET.SubElement(sp, "name").text = f"City_{city_idx}_Platform_{p_idx}"
            ET.SubElement(sp, "maximumTrainLength").text = "400"
            ET.SubElement(sp, "type").text = "Platform"

            # --- 2. Link Downstream Exit Signaling Nodes ---
            # RECIFE requires stopping points to maintain explicitly linked references
            # to any downstream signals governing departures from the platform block.
            signals_list_element = ET.SubElement(sp, "signals_List")

            # Execute a look-ahead spatial track walker to isolate bounding signaling nodes
            neighbor_signals = find_neighboring_signals(env, (r, c), signals_lookup)

            for sig_id in neighbor_signals:
                ET.SubElement(signals_list_element, "signal_RefId").text = sig_id

            # --- 3. Establish Spatial TDS Anchor Binding ---
            td_sections = ET.SubElement(sp, "TDSections")
            ET.SubElement(td_sections, "TDS_RefId").text = tds_ref

            # --- 4. Pipeline Logging Output ---
            sig_str = ", ".join(neighbor_signals) if neighbor_signals else "None found"
            print(f"{sp_id:<20} | R{r:>2}, C{c:>2}  | {track_nbr:<6} | {sig_str}")

            sp_count += 1

    print("-" * 75)
    print(f"[SUCCESS] {sp_count} StoppingPoints processed and added to XML.")
    print("=" * 75 + "\n")

    return extracted_platforms


def generate_stopping_groups_xml(infra_def_element, env):
    """
    Groups individual platforms (stopping points) into station groups per city.

    In RECIFE, 'stoppingPointsGroups' are used to define logical stations that consist
    of multiple physical platforms. This architectural grouping allows the MILP solver
    to flexibly reroute a train to an alternative available platform within the same
    station group if its default assignment is occupied during real-time traffic scheduling.

    Args:
        infra_def_element (xml.etree.ElementTree.Element): The XML root for InfrastructureDefinition.
        env (RailEnv): The Flatland environment containing 'agents_hints'.

    Returns:
        None (Modifies the infra_def_element XML tree in-place).
    """
    print("\n" + "=" * 75)
    print(f"{'--- Generating Stopping Points Groups (Stations) ---':^75}")
    print("=" * 75)

    # Retrieve procedural environmental hints from the Flatland layout
    hints = getattr(env, 'agents_hints', None)
    if not hints or 'train_stations' not in hints:
        print("[WARNING] No station data found. Skipping stopping groups.")
        return

    # Initialize the core XML container at the root level of the infrastructure tree
    groups_container = ET.SubElement(infra_def_element, "stoppingPointsGroups")
    train_stations = hints['train_stations']

    # Iterate over all procedurally generated cities to construct a logical station group for each
    for city_idx, platforms in enumerate(train_stations):
        group_id = f"Station_City_{city_idx}"

        # Populate core XML attributes for the structural stoppingPointsGroup node
        group = ET.SubElement(groups_container, "stoppingPointsGroup", stoGro_Id=group_id)
        ET.SubElement(group, "name").text = f"Station_{city_idx}"

        # Hardcode priority factor to 1 as required for standardized weight policies in the RECIFE solver
        ET.SubElement(group, "priorityFactor").text = "1"

        # Container for the list of physical platform references bound to this city group
        sp_list = ET.SubElement(group, "stoppingPoints_List")

        # Systematically parse and bind all individual platforms associated with this specific city
        for p_idx, (pos, _) in enumerate(platforms):
            r, c = pos

            # Reconstruct the exact unique identifier pattern established in 'generate_stopping_points_xml'
            sp_ref = f"SP_C{city_idx}_P{p_idx}_{r}_{c}"

            # Link the physical platform ID to this logical station collection container
            ET.SubElement(sp_list, "stoPo_RefId").text = sp_ref

        # Pipeline log tracking output for execution verification
        print(f"Group {group_id:<20} | Linked {len(platforms)} platforms.")

    print("-" * 75)
    print(f"[SUCCESS] {len(train_stations)} StoppingPointsGroups generated.")
    print("=" * 75 + "\n")


def generate_running_profiles_xml(infra_def_element):
    """
    Generates a default baseline running profile for the railway infrastructure.

    A running profile defines operational speed policies for trains (e.g., eco-driving,
    delayed recovery, or nominal max speed). This function instantiates a unrestricted
    'maxspeed' baseline profile. This forces the solver to evaluate travel velocity
    purely based on the physical track limits and explicitly defined operational journey
    running times, rather than artificial speed caps.

    Args:
        infra_def_element (xml.etree.ElementTree.Element): The XML root for InfrastructureDefinition.

    Returns:
        None (Modifies the infra_def_element XML tree in-place).
    """
    # Initialize the core XML container for global infrastructure speed profiles
    profiles_container = ET.SubElement(infra_def_element, "runningProfiles")

    # Define the baseline profile ID referenced during journey initialization
    profile = ET.SubElement(profiles_container, "runningProfile", runProfile_Id="maxspeed")
    ET.SubElement(profile, "name").text = "maxspeed"

    # Setting speed restriction to 'false' ensures that trains obey the natural track velocity limits,
    # letting the micro-running times injected downstream govern structural cell transit durations.
    ET.SubElement(profile, "speedRestriction").text = "false"

    print("--- [SUCCESS] Default RunningProfile 'maxspeed' generated. ---")


def generate_all_journeys_xml(infra_def_element, env, signals_lookup, platform_list):
    """
    Generates microscopic journey definitions between all valid platform permutations.

    This function utilizes a custom 4D Flatland DistanceMap to guide an A* pathfinding
    algorithm. It evaluates all initial heading vectors, filters out inefficient route
    choices exceeding the minimum cost threshold, and systematically explores
    alternative tracks by executing a k-shortest path variant using temporary edge-blocking.

    Args:
        infra_def_element (xml.etree.ElementTree.Element): The XML root for InfrastructureDefinition.
        env (RailEnv): The Flatland environment.
        signals_lookup (dict): Dictionary mapping (row, col, direction_out) to a Signal ID.
        platform_list (list): A list of tuples containing ((row, col), platform_id).

    Returns:
        dict: A routing database mapping generated journey IDs to their operational parameters
              (running times, stop patterns, cell paths, and TDS blocks).
    """
    journeys_container = ET.SubElement(infra_def_element, "journeys")
    all_infra_journeys = {}
    total_tds_across_all_paths = 0
    total_journeys_count = 0
    platform_lookup = {pos: p_id for pos, p_id in platform_list}
    stop_templates = {}

    # --- Configuration Constants ---
    # Maximum allowed length multiplier compared to the absolute shortest path
    PATH_LENGTH_TOLERANCE = 1.20

    # --- 1. DistanceMap Heuristic Initialization ---
    # Instantiated via mock destination agents to trigger full network matrix calculations
    mock_agents = [SimpleNamespace(target=pos) for pos, p_id in platform_list]

    custom_dist_map = DistanceMap(mock_agents, env.rail.grid.shape[0], env.rail.grid.shape[1])
    custom_dist_map.reset(mock_agents, env.rail)

    # Retrieve the 4D distance oracle tensor matrix: [target_index, row, col, direction]
    dist_data_full = custom_dist_map.get()
    print(f"--- Computed custom DistanceMap for {len(mock_agents)} targets ---")

    # Map unique platform identifiers to their respective index offsets inside the tensor
    platform_to_idx = {p_id: i for i, (pos, p_id) in enumerate(platform_list)}

    # --- 2. Process O(N^2) Platform Permutations ---
    for (start_pos, start_id), (end_pos, end_id) in itertools.permutations(platform_list, 2):

        # --- Intra-city Filter ---
        # Bypasses routing permutations between tracks located within the same local city boundaries
        # to restrict XML footprint bloat and minimize optimization solver parsing overhead.
        start_city = start_id.split('_')[1]
        end_city = end_id.split('_')[1]

        if start_city == end_city:
            continue

        target_idx = platform_to_idx[end_id]
        dist_data_for_this_target = dist_data_full[target_idx]

        # --- Phase 1: Collect Primitive Baselines Across Core Headings ---
        direction_paths = {}
        global_min_len = float('inf')

        for test_dir in range(4):
            # Evaluate only if an initial environmental track cell boundary breakout transition exists
            if env.rail.get_transitions((start_pos, test_dir)):
                shortest_path = find_path_astar(env, start_pos, end_pos, test_dir, dist_data_for_this_target)

                # Validate whether the path successfully targets destination coordinates without looping
                if shortest_path and shortest_path[-1][0] == end_pos:
                    if not is_path_valid(shortest_path):
                        print(f"[SKIP] Route {start_id} -> {end_id} (DIR {test_dir}): Internal loop detected.")
                        continue

                    direction_paths[test_dir] = shortest_path

                    # Track the absolute global minimum length discovered among heading combinations
                    if len(shortest_path) < global_min_len:
                        global_min_len = len(shortest_path)

        if not direction_paths:
            continue

        # --- Phase 2: Inefficiency Filtering & Alternative Path Exploration ---
        threshold_len = global_min_len * PATH_LENGTH_TOLERANCE

        for test_dir, base_path in direction_paths.items():

            # Drop baseline choices that deviate significantly from the network's optimal path length
            if len(base_path) > threshold_len:
                print(f"[FILTER] {start_id} -> {end_id} (DIR {test_dir}): "
                      f"Path too long ({len(base_path)} cells vs optimal {global_min_len}).")
                continue

            valid_paths = [base_path]
            max_allowed_len = len(base_path) * PATH_LENGTH_TOLERANCE

            # Generate alternative trajectory choices by systematically blocking one path edge segment at a time
            for i in range(len(base_path) - 1):

                u_pos, u_dir = base_path[i]
                v_pos, v_dir = base_path[i + 1]

                forbidden_edge = {(u_pos, v_pos)}
                alt_path = find_path_astar(env, start_pos, end_pos, test_dir, dist_data_for_this_target, forbidden_edge)

                # Validate whether the newly explored route satisfies length and loop constraints
                if alt_path and alt_path[-1][0] == end_pos and len(alt_path) <= max_allowed_len:
                    if is_path_valid(alt_path) and alt_path not in valid_paths:
                        valid_paths.append(alt_path)

            # --- Phase 3: Synchronize Intermediate Stops & Construct XML Objects ---
            template_key = f"{start_id}_TO_{end_city}"

            if template_key not in stop_templates:
                base_path = valid_paths[0]
                base_intermediate_platforms = [platform_lookup[pos] for pos, _ in base_path if
                                               pos != start_pos and pos != end_pos and pos in platform_lookup]

                required_stop_ids = []
                if base_intermediate_platforms:
                    k = np.random.randint(1, len(base_intermediate_platforms) + 1)
                    required_stop_ids = np.random.choice(base_intermediate_platforms, k,
                                                         replace=False).tolist()

                stop_templates[template_key] = required_stop_ids
            else:
                required_stop_ids = stop_templates[template_key]

            for path_idx, path in enumerate(valid_paths):
                base_id = f"J_{start_id}_TO_{end_id}_DIR_{test_dir}_ALT_{path_idx}"
                path_platforms = [platform_lookup[pos] for pos, _ in path if pos in platform_lookup]

                if not all(stop_id in path_platforms for stop_id in required_stop_ids):
                    continue

                path_selected_stops = []
                for i, (pos, _) in enumerate(path):
                    sp_id = platform_lookup.get(pos)
                    if sp_id in required_stop_ids:
                        path_selected_stops.append((i, sp_id))

                j_id, t_exp, t_loc, rel_times_loc = generate_journey_xml(
                    journeys_container, path, signals_lookup, env, start_pos, end_pos, start_id, end_id,
                    custom_id=base_id, local_stops_data=path_selected_stops
                )

                if j_id is not None:
                    path_with_tds = [(pos, f"TDS_{pos[0]}_{pos[1]}") for pos, _ in path]
                    all_infra_journeys[j_id] = {
                        'total_running_time_EXPRESS': t_exp,
                        'total_running_time_LOCAL': t_loc,
                        'stops_relative_times_LOCAL': rel_times_loc,
                        'local_stop_platforms': required_stop_ids,
                        'path': path,
                        'path_with_tds': path_with_tds
                    }

                    # Accumulate network metrics tracking data
                    # The length of the path directly maps to cell allocations (and thus active block counts)
                    total_tds_across_all_paths += len(path)
                    total_journeys_count += 1

    print(f"--- [SUCCESS] {len(all_infra_journeys)} journeys added to the XML ---")

    # ==========================================
    # DATA VALIDATION SUMMARY REPORT
    # ==========================================
    print("\n[DEBUG POST 1] --- Infrastructure Handover ---")
    print(f"Number of generated routes in all_infra_journeys: {len(all_infra_journeys)}")

    if total_journeys_count > 0:
        avg_tds_per_journey = total_tds_across_all_paths / total_journeys_count
        print("\n" + "=" * 30)
        print(f"ROUTING STATISTICS:")
        print(f"Total Journeys Generated: {total_journeys_count}")
        print(f"Average TDS length per Journey: {avg_tds_per_journey:.2f}")
        print(f"AVG_TDS_REPORT: {avg_tds_per_journey:.2f}")
        print("=" * 30 + "\n")

    return all_infra_journeys


def generate_journey_xml(infra_journeys_container, path_cells, signals_lookup, env, start_node, end_node, start_sp_id,
                         end_sp_id, custom_id=None, local_stops_data=None):
    """
    Translates a sequence of grid cells (an A* path) into a RECIFE <journey> XML structure.

    This function constructs the complete hierarchy required for a train route:
    1. 'blockSequence': The logical sequence of interlocking blocks the train claims.
    2. 'journeyInstances': The specific rolling stock assignment and running profile.
    3. 'stoppingSequence': The origin, intermediate, and destination station assignments.
    4. 'journeyInstanceTDSDetails': The physical cell-by-cell breakdown, including
       simulated acceleration and deceleration running times near stops.

    Args:
        infra_journeys_container (xml.etree.ElementTree.Element): The parent <journeys> XML element.
        path_cells (list): List of tuples representing the path: [((row, col), direction_in), ...].
        signals_lookup (dict): Dictionary mapping (row, col, direction_out) to a Signal ID.
        env (RailEnv): The Flatland environment.
        start_node (tuple): The (row, col) coordinates of the starting platform.
        end_node (tuple): The (row, col) coordinates of the destination platform.
        start_sp_id (str): The ID of the starting Stopping Point (Platform).
        end_sp_id (str): The ID of the destination Stopping Point (Platform).
        custom_id (str, optional): A unique ID for the journey. Generates a default if None.
        local_stops_data (list, optional): List of tuples containing (path_index, stopping_point_id).

    Returns:
        tuple: (journey_id (str), t_exp (int), t_loc (int), rel_times_loc (list)) containing
               the journey identifier, total express running time, total local running time,
               and relative arrival timelines at intermediate stations.
    """
    # Initialize the local stops container if none is explicitly provided
    if local_stops_data is None:
        local_stops_data = []

    # Establish a standardized, unique identifier for the journey node
    if custom_id:
        journey_id = custom_id
    else:
        journey_id = f"J_{start_node[0]}_{start_node[1]}_TO_{end_node[0]}_{end_node[1]}"

    journey = ET.SubElement(infra_journeys_container, "journey", journey_Id=journey_id)
    ET.SubElement(journey, "name").text = f"Route from {start_node} to {end_node}"

    # ==========================================
    # 1. Build the Block Sequence
    # ==========================================
    block_seq_container = ET.SubElement(journey, "blockSequence")
    xml_index = 0

    # --- 1A. Identify and add the Virtual Start Block ---
    # RECIFE requires trains spawning at platforms to enter the active grid via a virtual block
    (r_start, c_start), d_out_start = path_cells[0]
    exit_sig_start = signals_lookup.get((r_start, c_start, d_out_start))

    if exit_sig_start:
        # ID pattern must strictly match the naming convention established in generate_blocks_xml
        virtual_block_id = f"VIRTUAL_BLOCK_TO_{exit_sig_start}"

        elmt = ET.SubElement(block_seq_container, "blockSeqElmt", index=str(xml_index))
        ET.SubElement(elmt, "blockSection_RefId").text = virtual_block_id
        xml_index += 1
    else:
        print(f"[WARNING] Virtual block assignment failed: No departure signal found at platform {start_node}.")

    # --- 1B. Map the Physical Interlocking Blocks ---
    for i in range(len(path_cells) - 1):
        (r, c), d_in_current = path_cells[i]
        (nr, nc), d_in_next = path_cells[i + 1]

        # The signal granting entry to the next cell (located at the exit boundary of the current cell)
        entry_sig = signals_lookup.get((r, c, d_in_next))

        # The signal guarding the exit boundary of the targeted next cell block
        if i + 2 < len(path_cells):
            # If additional cells remain downstream, retrieve the next transition direction
            (_, _), d_in_after = path_cells[i + 2]
            exit_sig = signals_lookup.get((nr, nc, d_in_after))
        else:
            # If targeting the final cell (destination platform), default to the final arrival heading
            exit_sig = signals_lookup.get((nr, nc, d_in_next))

        if entry_sig and exit_sig:
            block_id = f"BLOCK_{entry_sig}_TO_{exit_sig}"
            elmt = ET.SubElement(block_seq_container, "blockSeqElmt", index=str(xml_index))
            ET.SubElement(elmt, "blockSection_RefId").text = block_id
            xml_index += 1

    # ==========================================
    # 2. Build Journey Instances (EXPRESS & LOCAL service profiles)
    # ==========================================
    instances_container = ET.SubElement(journey, "journeyInstances")

    def build_instance(service_type, stops_data):
        """Helper to construct structural elements for explicit commercial service profiles."""
        inst_id = f"{journey_id}_{service_type}___CL"
        instance = ET.SubElement(instances_container, "journeyInstance", jouInst_Id=inst_id)

        # 'CL' maps to a standard rolling stock type template parsed by the solver
        ET.SubElement(instance, "rolSto_RefId").text = "CL"

        stop_seq = ET.SubElement(instance, "stoppingSequence")

        # Define Origin Station reference node
        stop_start = ET.SubElement(stop_seq, "stopSeqElmt", index="0")
        ET.SubElement(ET.SubElement(stop_start, "stoppingAt"), "stoPo_refId").text = start_sp_id
        ET.SubElement(stop_start, "stoppingType").text = "Origin"

        # Define Intermediate Station nodes
        cur_idx = 1
        stop_indices = set()
        for path_idx, sp_id in stops_data:
            stop_elmt = ET.SubElement(stop_seq, "stopSeqElmt", index=str(cur_idx))
            ET.SubElement(ET.SubElement(stop_elmt, "stoppingAt"), "stoPo_refId").text = sp_id
            ET.SubElement(stop_elmt, "stoppingType").text = "Intermediate"
            stop_indices.add(path_idx)
            cur_idx += 1

        # Define Destination Station reference node
        stop_end = ET.SubElement(stop_seq, "stopSeqElmt", index=str(cur_idx))
        ET.SubElement(ET.SubElement(stop_end, "stoppingAt"), "stoPo_refId").text = end_sp_id
        ET.SubElement(stop_end, "stoppingType").text = "Destination"

        tds_details = ET.SubElement(instance, "journeyInstanceTDSDetails", runningProfile_RefId="maxspeed")
        tot_time = 0
        rel_times = []
        tot_cells = len(path_cells)

        # Iterate step-by-step through the layout path to allocate section running times
        for idx, (pos, d_in) in enumerate(path_cells):
            detail = ET.SubElement(tds_details, "journeyInstanceTDSDetail", index=str(idx))
            ET.SubElement(detail, "TDS_RefId").text = f"TDS_{pos[0]}_{pos[1]}"

            # --- Microscopic Braking / Acceleration Simulation Penalties ---
            # Simulate physical deceleration and acceleration slopes by padding cell transit times.
            # Applied if a cell bounds an active station stop or is near a route boundary.
            is_near_stop = (idx <= 1) or ((tot_cells - 1 - idx) <= 1)
            if not is_near_stop:
                if any(abs(idx - s_idx) <= 1 for s_idx in stop_indices):
                    is_near_stop = True

            # Impose a 45-second penalty for cells flanking commercial stopping points
            act_run_time = 45 if is_near_stop else get_running_time(env, pos)
            tot_time += act_run_time

            # Log relative travel timeline when hitting scheduled intermediate stops
            if any(idx == s_idx for s_idx, _ in stops_data):
                rel_times.append(tot_time)

            ET.SubElement(detail, "runningTime").text = str(act_run_time)
            ET.SubElement(detail, "clearingTime").text = "5"

            # Associate active cells to their physical station platform references where applicable
            if pos == end_node:
                ET.SubElement(detail, "stoPo_RefId").text = end_sp_id
            elif pos == start_node:
                ET.SubElement(detail, "stoPo_RefId").text = start_sp_id
            else:
                # Map intermediate stop indices to the operational trajectory matrix
                for s_idx, sp_id in stops_data:
                    if idx == s_idx:
                        ET.SubElement(detail, "stoPo_RefId").text = sp_id
                        break
            ET.SubElement(detail, "occupiedTDS")

        return tot_time, rel_times

    # Construct separate instances for commercial EXPRESS and LOCAL operational profiles
    t_exp, _ = build_instance("EXPRESS", [])
    t_loc, rel_times_loc = build_instance("LOCAL", local_stops_data)

    return journey_id, t_exp, t_loc, rel_times_loc

def scan_platform_locations(env):
    """
    Scans the Flatland environmental layout to isolate station platform coordinates
    and generates unique infrastructure Stopping Point IDs.

    This utility function parses the nested 'agents_hints' tracking object generated by
    Flatland's schedule generator. It yields a standardized collection of registered
    platforms required downstream for routing validation and structural XML element binding.

    Args:
        env (RailEnv): The initialized Flatland environment object.

    Returns:
        list: A list of tuples containing coordinate pairs and their corresponding ID strings:
              [((row, col), sp_id), ...]. Returns an empty list if no station nodes exist.
    """
    extracted_platforms = []

    # Safely retrieve procedural layout hints embedded within the environment
    hints = getattr(env, 'agents_hints', None)

    # Abort execution gracefully if the underlying model lacks valid station coordinates
    if not hints or 'train_stations' not in hints:
        print("[WARNING] No 'train_stations' found in environment hints.")
        return []

    train_stations = hints['train_stations']

    # Traversed systematically through the nested grid matrix dictionary collection
    for city_idx, platforms in enumerate(train_stations):
        for p_idx, (pos, track_nbr) in enumerate(platforms):
            r, c = pos

            # Establish a unique, uniform key formatting pattern used across the pipeline
            # Blueprint layout: SP_C{CityIndex}_P{PlatformIndex}_{Row}_{Col}
            sp_id = f"SP_C{city_idx}_P{p_idx}_{r}_{c}"

            extracted_platforms.append((pos, sp_id))

    return extracted_platforms

def find_path_astar(env, start_pos, target_pos, start_dir, dist_data, forbidden_edges=None):
    """
    Finds the shortest valid path between two coordinates using the A* algorithm.

    This implementation leverages a pre-computed Flatland DistanceMap as its
    heuristic function (h-score) to ensure highly efficient pathfinding. It also
    supports edge-blocking (forbidden_edges) to force the algorithm to route
    around specific track sections, allowing for the generation of alternative routes.

    Args:
        env (RailEnv): The Flatland environment.
        start_pos (tuple): The (row, col) starting coordinates.
        target_pos (tuple): The (row, col) destination coordinates.
        start_dir (int): The initial heading direction (0: N, 1: E, 2: S, 3: W).
        dist_data (numpy.ndarray): The 3D heuristic distance matrix for the target.
        forbidden_edges (set, optional): A set of ((u_r, u_c), (v_r, v_c)) tuples
                                         representing edges that cannot be traversed.

    Returns:
        list: A path represented as a list of tuples [((row, col), direction_in), ...],
              or None if no valid path exists.
    """
    if forbidden_edges is None:
        forbidden_edges = set()

    # Retrieve the initial heuristic estimate (distance to the targeted platform)
    # Note: dist_data operates as an oracle tensor indexed by [row, col, direction]
    start_h = dist_data[start_pos[0], start_pos[1], start_dir]

    # If the initial heuristic returns infinity, the target is structurally unreachable
    if start_h == np.inf:
        return None

    # The priority queue maps the exploration frontier using tuples formatted as:
    # (f_score, g_score, current_position, current_direction, path_history_list)
    # Headpop operations systematically extract the state with the lowest f_score.
    queue = [(start_h, 0, start_pos, start_dir, [(start_pos, start_dir)])]

    # Track visited states to prevent cyclical infinite loops.
    # CRITICAL: In railway routing, a unique state must combine BOTH cell position
    # and facing direction, as overlapping tracks permit separate directional crossings.
    visited = set()

    while queue:
        # Pop the state containing the lowest estimated total cost (f = g + h)
        f, g, curr_pos, curr_dir, path = heapq.heappop(queue)

        # --- Base Case: Target Destination Reached ---
        if curr_pos == target_pos:
            return path

        state = (curr_pos, curr_dir)
        if state in visited:
            continue
        visited.add(state)

        # Isolate the allowed track cell transitions based on the incoming heading orientation
        possible_transitions = env.rail.get_transitions((curr_pos, curr_dir))

        # Mathematical inversion to calculate the exact backward heading vector (0->2, 1->3, etc.)
        # Flatland rolling stock agents cannot execute an instantaneous 180-degree U-turn inside a cell.
        inverse_dir = (curr_dir + 2) % 4

        # Evaluate all 4 potential exit direction transitions
        for d_out in range(4):
            # Process option only if an active track path exists and avoids an illegal U-turn flip
            if possible_transitions[d_out] and d_out != inverse_dir:
                next_pos = get_new_position(curr_pos, d_out)

                # --- Edge-Blocking Constraint Evaluation ---
                # Bypasses restricted paths to force alternative route exploratory generation
                if (curr_pos, next_pos) in forbidden_edges:
                    continue

                # Retrieve the look-ahead heuristic distance from the neighbor to the target
                h = dist_data[next_pos[0], next_pos[1], d_out]

                # Advance path exploration only if the target remains accessible from the neighbor node
                if h != np.inf:
                    new_g = g + 1  # Standard step cost weight incremented by 1 cell segment
                    new_f = new_g + h

                    # Append valid neighbor data onto the priority exploration heap frontier
                    heapq.heappush(queue, (new_f, new_g, next_pos, d_out, path + [(next_pos, d_out)]))

    # Return None if the frontier queue empties entirely without intersecting the destination node
    return None

def get_running_time(env, pos):
    """
    Determines the baseline macro running time for a train traversing a specific grid cell.

    This function evaluates the physical complexity of a cell by calculating the
    total number of valid internal track transitions. It inspects Flatland's
    underlying 16-bit binary cell register: a standard bidirectional track segment
    (straight line or static curve) contains at most 2 active bits, whereas
    complex infrastructure nodes (turnout switches or diamond crossings) possess more.

    Args:
        env (RailEnv): The initialized Flatland environment object.
        pos (tuple): The (row, col) matrix coordinates of the targeted grid cell.

    Returns:
        int: The baseline operational running time allocated for the cell block in seconds.
    """
    # Baseline operational running time values (configured in seconds).
    # Structured as a dictionary to permit straightforward downstream adjustments
    # for geometric line curvatures or vertical gradient parameters.
    # Initially straight and switch TDS were given different running times but this is no longer the case
    CELL_TYPE_SPEEDS = {
        'straight': 30,
        'switch': 30
    }

    # Retrieve the 16-bit integer mask encoding all valid path movements through this node
    transitions = env.rail.get_full_transitions(*pos)

    # Calculate the Hamming weight (total active '1' bits) to evaluate layout complexity
    num_transitions = bin(transitions).count('1')

    # A standard bidirectional track segment features a maximum configuration weight of 2 bits
    if num_transitions <= 2:
        return CELL_TYPE_SPEEDS['straight']
    else:
        # A bit count greater than 2 indicates a high-complexity interlocking junction (switch or crossing)
        return CELL_TYPE_SPEEDS['switch']

def is_path_valid(path_cells):
    """
    Validates a generated path trajectory by checking for overlapping grid cells (loops).

    A valid train route in RECIFE cannot intersect itself. This function strips out
    the directional orientation data and evaluates purely the physical 2D grid matrix
    coordinates to mathematically guarantee that no cell is traversed more than once.

    Args:
        path_cells (list): A list of path tuples formatted as:
                           [((row, col), direction_in), ...].

    Returns:
        bool: True if the path contains no self-intersecting loops, False if it contains
              duplicate cell coordinates or if the path structure is empty.
    """
    # An empty path sequence contains no valid traversal steps and is inherently invalid
    if not path_cells:
        return False

    # Extract purely the (row, col) spatial coordinate pairs from the composite tracking tuples
    cells_only = [pos for pos, direction in path_cells]

    # Utilizing a Python 'set' invokes a hash-table collection that discards duplicate elements.
    # If the length of the deduplicated set matches the length of the original coordinate list,
    # it mathematically proves that every spatial node in the route is completely unique.
    return len(cells_only) == len(set(cells_only))

def find_neighboring_signals(env, start_pos, signals_lookup):
    """
    Simulates a spatial forward 'walk' along the track topology from a platform cell
    in all valid directions to locate the nearest physical departure signals.

    In RECIFE, stopping points (platforms) must maintain explicit structural references
    to the specific signaling devices that protect and regulate entry into their
    adjacent interlocking block sections. This function traces operational track paths
    step-by-step until an exit signal is discovered or a protective distance threshold is met.

    Args:
        env (RailEnv): The initialized Flatland environment object.
        start_pos (tuple): The (row, col) matrix coordinates of the targeted station platform.
        signals_lookup (dict): Dictionary mapping (row, col, direction_out) to a unique Signal ID.

    Returns:
        list: A deduplicated collection of unique Signal ID strings guarding departures from the platform.
    """
    r, c = start_pos
    found_signals = []

    # --- 1. Identify Valid Departure Directions ---
    # Flatland station complexes are typically positioned on linear, non-diverging track segments
    # (oriented either North-South or East-West). The pipeline evaluates all transition vectors
    # to extract the physically valid exit headings supported by the cell's underlying rails.
    all_possible_directions = []

    for d_in in range(4):
        # Query track choices using Flatland's explicit cell-direction state syntax tuple: ((r, c), d_in)
        trans = env.rail.get_transitions(((r, c), d_in))
        for d_out in range(4):
            if trans[d_out] and d_out not in all_possible_directions:
                all_possible_directions.append(d_out)

    # --- 2. Execute Look-Ahead Spatial Track Tracing ---
    # Initiate an independent outward path walker for each isolated departure heading vector
    for start_dir in all_possible_directions:
        visited = {(r, c)}
        curr_pos = start_pos
        curr_dir = start_dir

        # Limit tracking length to 50 cells to prevent infinite looping conditions on tight circular tracks
        for _ in range(50):

            # Verify whether a signaling device exists at the exit boundary of the current node
            if (curr_pos[0], curr_pos[1], curr_dir) in signals_lookup:
                found_signals.append(signals_lookup[(curr_pos[0], curr_pos[1], curr_dir)])
                break

            # Translate coordinates forward along the active trajectory heading vector
            next_pos = get_new_position(curr_pos, curr_dir)

            # Terminate path tracing if the walker exits grid bounds or encounters a cyclic duplicate node
            if next_pos is None or next_pos in visited:
                break

            # Determine the subsequent steering heading vector required to enter the adjacent cell.
            # Rationale: This phase assumes the initial track linking a platform block to its
            # guarding signal is linear and does not branch into diverging turnout switches.
            next_trans = env.rail.get_transitions((next_pos, curr_dir))

            if sum(next_trans) == 0:
                break  # Dead end or unresolvable terminal track buffers intersected

            # Utilize argmax to isolate the index array bit corresponding to the active exit vector
            curr_dir = np.argmax(next_trans)
            curr_pos = next_pos
            visited.add(curr_pos)

    # Return a completely deduplicated set collection of the discovered signal keys
    return list(set(found_signals))

if __name__ == "__main__":
    # --- COMMAND LINE ARGUMENTS ---
    parser = argparse.ArgumentParser(description="RECIFE XML Infrastructure and Timetable Generator Pipeline")
    parser.add_argument("--mode", type=str, choices=["both", "infra", "timetable"], default="both",
                        help="Execution mode: 'both' (generate complete dataset), 'infra' (infrastructure layer only), or 'timetable' (operational layer only)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Unique pseudo-random seed assigned for this specific batch instance iteration")
    args = parser.parse_args()

    INSTANCE_SEED = args.seed
    INSTANCE_NAME = f"Instance_{INSTANCE_SEED:03d}"
    INPUT_DIR = os.path.join(INSTANCE_NAME, "inputData")
    OUTPUT_DIR = os.path.join(INSTANCE_NAME, "outputFiles")

    # Establish structural directory environment trees
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Initialize systematic global seeding states to guarantee runtime determinism
    random.seed(INSTANCE_SEED)
    np.random.seed(INSTANCE_SEED)

    print(f"--- 1. Starting Flatland Environment (Mode: {args.mode.upper()}) ---")
    print("\n" + "=" * 75)
    print(f"{'--- 1. INITIALIZING FLATLAND ENVIRONMENT ---':^75}")
    print("=" * 75)

    # --- Configuration Parameters ---
    # Note: These parameters must strictly match the layout templates configured across the extension models.
    GRID_WIDTH = 55
    GRID_HEIGHT = 55
    N_CITIES = 6
    SEED = INSTANCE_SEED
    CONFIGURATION = [6, 3, 3, 2, 2, 2]

    # Target number of valid train courses required to schedule in the final optimization matrix.
    N_AGENTS_TARGET = 40
    MAX_ATTEMPTS = 30
    PERTURBATION_RANGE = (300, 900)
    PERTURBATION_FRACTION = 0.4

    # Oversampling pool configuration: Instantiate a wide 10x target baseline volume of candidate agents.
    # This ensures a rich reserve pool remains available to replenish the active fleet as unfeasible paths
    # and spatial conflicts get iteratively stripped away by the downstream rejection filters.
    N_AGENTS_INITIAL = 10 * N_AGENTS_TARGET

    # Initialize the custom structural Flatland framework wrapper helper
    env_helper = FlatlandEnvironmentHelper(
        grid_width=GRID_WIDTH,
        grid_height=GRID_HEIGHT,
        number_of_agents=N_AGENTS_INITIAL,
        n_cities=N_CITIES,
        city_track_counts=CONFIGURATION,
        random_seed=SEED,
    )
    print(
        f"PARAM_REPORT: Width={GRID_WIDTH}, Height={GRID_HEIGHT}, Cities={N_CITIES}, Agents={N_AGENTS_TARGET}, Initial agents={N_AGENTS_INITIAL}, Max attempts iteration cycle={MAX_ATTEMPTS}, Configuration={CONFIGURATION}, Perturbation duration={PERTURBATION_RANGE}, Perturbation fraction={PERTURBATION_FRACTION}")
    env = env_helper.get_rail_env()

    # ============================================================
    # DATA EXTRACTION: RETRIEVING SPARSERAILGEN HINTS
    # ============================================================
    print("\n--- Extracting hidden station data from SparseRailGenerator ---")

    # Intercept and call the underlying layout generation function directly on the SparseRailGen hook.
    # The return signature unpacks as a dual tuple mapping: (grid_map, configuration_hints_dict)
    _, all_hints = env.rail_generator.generate(
        width=GRID_WIDTH,
        height=GRID_HEIGHT,
        num_agents=N_AGENTS_INITIAL,
        num_resets=0,
        np_random=env.np_random  # Synchronize using the environment's current random state for consistency
    )

    # Map the deeply nested layout coordinates into the active execution frame memory state
    if all_hints and 'agents_hints' in all_hints:
        env.agents_hints = all_hints['agents_hints']
        train_stations = env.agents_hints['train_stations']
        print(f"ACTUAL_CITIES_PLACED: {len(train_stations)}")
        print(f"[SUCCESS] Extracted {len(train_stations)} cities populated with platform topology nodes.")

        # Print structural platform mapping configurations for log tracking and verification
        for city_idx, platforms in enumerate(train_stations):
            print(f"  City {city_idx} contains {len(platforms)} platform(s):")
            for p_idx, (pos, track_nbr) in enumerate(platforms):
                print(f"    -> Platform {p_idx} located at grid cell {pos}")
    else:
        print("[ERROR] Infrastructure generator returned empty structural hint data dictionaries. Check environment scaling boundaries.")
    # ============================================================

    # Define standardized serialization file paths for local infrastructure caching
    CACHE_FILE = os.path.join(INPUT_DIR, "infra_cache.pkl")

    # ============================================================
    # 2. ENVIRONMENT VISUALIZATION & TOPOLOGY ANALYSIS
    # ============================================================
    if args.mode in ["both", "infra"]:
        print("\n" + "=" * 75)
        print(f"{'--- 2. ENVIRONMENT VISUALIZATION ---':^75}")
        print("=" * 75)

        VISUALIZATION = False
        if VISUALIZATION:
            print("(Dismiss the active image plot window manually to unblock pipeline execution...)")

            try:
                # Initialize Flatland's native rendering abstraction using the PILSVG background engine
                env_renderer = RenderTool(env, gl="PILSVG")
                env_renderer.render_env(show=True, show_observations=False, show_predictions=False)
                image = env_renderer.get_image()

                # Pipe the rendered environment pixel matrix array into Matplotlib for standard output scaling
                plt.figure(figsize=(10, 10))
                plt.imshow(image)
                plt.title(f"Flatland Grid ({GRID_HEIGHT}x{GRID_WIDTH}) - {N_CITIES} Cities")
                plt.axis('off')
                plt.show()
            except Exception as e:
                print(f"[WARNING] Environmental UI visualization layer encountered an exception or was bypassed: {e}")

        # ============================================================
        # 3. XML GENERATION (INFRASTRUCTURE LAYER)
        # ============================================================
        print("\n" + "=" * 75)
        print(f"{'--- 3. GENERATING RECIFE INFRASTRUCTURE XML ---':^75}")
        print("=" * 75)

        # Initialize the structural root XML Element for the RECIFE mapping schema
        recife_objects = ET.Element("recifeObjects")

        # Construct the primary Infrastructure Definition top-level container

        # Construct the primary Infrastructure Definition top-level container
        # The infrastructure_Id is dynamically linked to the unique instance seed to prevent database collisions
        infra_id = f"Flatland_Gen_{INSTANCE_SEED:03d}"
        infra_def = ET.SubElement(recife_objects, "InfrastructureDefinition", infrastructure_Id=infra_id)
        ET.SubElement(infra_def, "name").text = f"Flatland_Generated_Infrastructure_{INSTANCE_SEED:03d}"
        ET.SubElement(infra_def,
                      "description").text = f"Automated microscopic export from Flatland SparseRailGenerator using seed {INSTANCE_SEED}"

        # Step 0: Extract Platform Locations (No XML generated yet)
        platform_list = scan_platform_locations(env)

        # Step 1: Track Detection Sections (TDS)
        generate_full_tds_xml(env, infra_def, platform_list)

        # Step 2: Signals
        signals_lookup = generate_signals_xml(infra_def, env)

        # Step 3: Interlocking Blocks
        generate_blocks_xml(infra_def, env, signals_lookup, platform_list)

        # Step 4: Stopping Points (Individual Platforms)
        generate_stopping_points_xml(infra_def, env, signals_lookup)

        # Step 5: Stopping Points Groups (Stations/Cities)
        generate_stopping_groups_xml(infra_def, env)

        # Step 6: Default Running Profiles
        generate_running_profiles_xml(infra_def)

        # Step 7: Journeys (Routing between platforms via A*)
        all_infra_journeys = generate_all_journeys_xml(infra_def, env, signals_lookup, platform_list)

        # --- NEW: Save calculated journeys and platforms in cache ---
        with open(CACHE_FILE, "wb") as f:
            pickle.dump({"platforms": platform_list, "journeys": all_infra_journeys}, f)
        print(
            f"\n[SUCCESS] Extracted platform nodes and optimized journey paths successfully cached in '{CACHE_FILE}'.")

        # ============================================================
        # 4. PHYSICAL FILE EXPORT
        # ============================================================
        print("\n--- 4. Exporting Infrastructure XML File ---")
        infra_filename = os.path.join(INPUT_DIR, "real_infrastructure.xml")

        # Enforce clear visual formatting across the generated XML hierarchy tree where supported
        try:
            ET.indent(recife_objects, space="  ", level=0)
        except AttributeError:
            pass

        xml_str = ET.tostring(recife_objects, encoding='unicode')

        # Commit structured infrastructure layout data directly to disk
        with open(infra_filename, "w", encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(xml_str)

        print(f"[SUCCESS] Infrastructure saved as '{infra_filename}'.")

    # ============================================================
    # 5. TIMETABLE GENERATION LAYER INITIALIZATION
    # ============================================================
    if args.mode in ["both", "timetable"]:
        print("\n" + "=" * 75)
        print(f"{'--- 5. INITIALIZING RECIFE OPERATIONAL TIMETABLE LAYER ---':^75}")
        print("=" * 75)

        # --- Standalone Mode Cache Evaluation ---
        # When bypassing the infrastructure build phase, retrieve structural mappings
        # directly from the local cache file to eliminate pathfinding computation loops.
        if args.mode == "timetable":
            if not os.path.exists(CACHE_FILE):
                print(f"[ERROR] Serialization cache missing at target: '{CACHE_FILE}'\n"
                      f"        Execution aborted. Execute pipeline using '--mode both' or '--mode infra' "
                      f"        at least once to establish topology baselines.")
                exit(1)

            with open(CACHE_FILE, "rb") as f:
                cache_data = pickle.load(f)
                platform_list = cache_data["platforms"]
                all_infra_journeys = cache_data["journeys"]
            print(f"[SUCCESS] Infrastructure topology matrix successfully retrieved from cache link: '{CACHE_FILE}'.")

        # ============================================================
        # 6. SPAWN ORIENTATION OPTIMIZATION (180-DEGREE FLIP)
        # ============================================================
        print("\n" + "=" * 75)
        print(f"{'--- 6. OPTIMIZING AGENT STARTING DIRECTIONS ---':^75}")
        print("=" * 75)

        optimized_agents = []
        platform_lookup = {pos: p_id for pos, p_id in platform_list}

        for agent in env.agents:
            start_sp_id = platform_lookup.get(agent.initial_position)
            end_sp_id = platform_lookup.get(agent.target)

            if not start_sp_id or not end_sp_id:
                continue

            # --- Step 1: Validate Current Spawn Orientation ---
            # Evaluate if the native initial direction yields a valid microscopic journey route
            # (Note: Inefficient paths exceeding the 1.20x tolerance factor were stripped out during infra generation)
            current_base = f"J_{start_sp_id}_TO_{end_sp_id}_DIR_{agent.initial_direction}"
            has_current_route = any(j.startswith(current_base) for j in all_infra_journeys)

            if has_current_route:
                # The default assigned initial direction is valid, efficient, and cleared for scheduling
                optimized_agents.append(agent)
            else:
                # --- Step 2: Apply 180-Degree Flip Evaluation ---
                # If the default vector is unfeasible, check the exact opposite heading track alignment.
                opposite_dir = (agent.initial_direction + 2) % 4
                opposite_base = f"J_{start_sp_id}_TO_{end_sp_id}_DIR_{opposite_dir}"

                # Verify if the inverted heading matches a validated, pre-calculated journey vector
                if any(j.startswith(opposite_base) for j in all_infra_journeys):
                    print(f"  [SWAP ORIENTATION] Agent mapping {agent.initial_position} -> {agent.target}: "
                          f"Inverting direction vector {agent.initial_direction} -> {opposite_dir} (Valid path isolated).")
                    agent.initial_direction = opposite_dir
                    optimized_agents.append(agent)
                else:
                    # No valid journey exists in either direction
                    print(f"  [DISCARD] Agent at cell position {agent.initial_position}: "
                          f"No compliant route found across primary or inverted spawn orientation vectors.")

        # Synchronize the active environment's internal array state with the optimized rolling stock pool
        env.agents = optimized_agents

        print(f"\n[SUCCESS] Retained {len(env.agents)} optimized agents.")

        # ============================================================
        # 7. STOCHASTIC UNIFORM DEPARTURE TIME DISTRIBUTION
        # ============================================================
        print("\n---7. Applying Stochastic Uniform Departure Times ---")
        # 120 steps define a 1-hour macro window based on Flatland's operational metric (1 step = 30 seconds)
        FIXED_DEPARTURE_WINDOW = 120
        num_final_agents = len(env.agents)

        if num_final_agents > 0:
            # Generate pseudo-random departure offsets uniformly distributed across the operational window.
            # CRITICAL: Because np.random.seed(INSTANCE_SEED) was instantiated at pipeline initialization,
            # this distribution profile remains fully deterministic and reproducible per benchmark instance.
            departure_steps = np.random.randint(0, FIXED_DEPARTURE_WINDOW + 1, size=num_final_agents)

            for i, agent in enumerate(env.agents):
                # Assign the stochastically selected timeline offset to the agent's release register
                agent.earliest_departure = int(departure_steps[i])

        print(f"[SUCCESS] Assigned stochastic departure times over {FIXED_DEPARTURE_WINDOW} steps.")

        # ============================================================
        # 8. ROLLING STOCK MATCHMAKER
        # ============================================================
        print("\n" + "=" * 75)
        print(f"{'--- 8. CALCULATING ROLLING STOCK CONNECTIONS ---':^75}")
        print("=" * 75)

        platform_lookup = {pos: p_id for pos, p_id in platform_list}
        course_list = []

        for idx, agent in enumerate(optimized_agents):
            start_pos = agent.initial_position
            end_pos = agent.target

            start_platform_id = platform_lookup.get(start_pos)
            end_platform_id = platform_lookup.get(end_pos)

            if not start_platform_id or not end_platform_id:
                continue

            # Extract macro city node identifiers from structural platform keys
            start_city = start_platform_id.split('_')[1]
            end_city = end_platform_id.split('_')[1]

            # Stochastic rolling stock prioritization: Allocate a 20% baseline probability for premium Express vectors
            is_express = np.random.random() < 0.20
            service_type = "EXPRESS" if is_express else "LOCAL"

            # Baseline Unix-equivalent timestamp offset set to 08:00 AM (28,800 seconds)
            base_time_sec = 28800
            step_duration_sec = 30
            dwell_time_origin = 30

            # Calculate the absolute departure timestamp by accumulating stochastically assigned step offsets
            dep_time = base_time_sec + (agent.earliest_departure * step_duration_sec)

            # Dynamic Route Profile Matching: Query the pre-calculated A* micro-routing database
            expected_base = f"J_{start_platform_id}_TO_{end_platform_id}_DIR_{agent.initial_direction}"
            matching_journey_key = next((j_id for j_id in all_infra_journeys.keys() if j_id.startswith(expected_base)),None)

            if matching_journey_key:
                # Extract basic running time parameters matching the assigned commercial speed class
                expected_travel_time = all_infra_journeys[matching_journey_key][f'total_running_time_{service_type}']

                # For non-express services, append localized station deceleration/dwell penalties (30s per stop)
                if service_type == "LOCAL":
                    number_of_stops = len(
                        all_infra_journeys[matching_journey_key].get('stops_relative_times_LOCAL', []))
                    expected_travel_time += (number_of_stops * 30)
            else:
                expected_travel_time = 1800  # Fallback safety

            # Compile total elapsed travel time to establish the absolute arrival timestamp
            arr_time = dep_time + dwell_time_origin + expected_travel_time

            # Construct the structural dictionary object required to serialize RECIFE course layers
            course = {
                'course_id': f"COURSE_AGENT_{idx}_{service_type}",
                'start_city': start_city,
                'end_city': end_city,
                'start_platform': start_platform_id,
                'end_platform': end_platform_id,
                'dep_time': int(dep_time),
                'arr_time': int(arr_time),
                'agent_obj': agent,  # Maintain explicit reference to the underlying Flatland agent object instance
                'journey_id': matching_journey_key,
                'service_type': service_type
            }

            course_list.append(course)
        # ============================================================
        # 9. ITERATIVE ROSTER BUILDING & FEASIBILITY FILTERING
        # ============================================================
        print("\n" + "=" * 75)
        print(f"{f'--- 9. ITERATIVE ROSTER BUILDING (TARGET:{N_AGENTS_TARGET}) ---':^75}")
        print("=" * 75)

        # Segment the global course array into an initial active working roster and a standby reserve pool
        active_roster = course_list[:N_AGENTS_TARGET]
        reserve_pool = course_list[N_AGENTS_TARGET:]

        final_valid_courses = []
        final_valid_connections = []

        attempt = 1

        while len(active_roster) == N_AGENTS_TARGET:
            print(f"\n[ATTEMPT {attempt}] Evaluating candidate roster compliance for {N_AGENTS_TARGET} trains...")

            # --- Step 1: Establish Memory Isolated Deep Copy ---
            # Because the downstream connection builder dynamically overwrites platform assignments
            # and path configurations, we isolate a deep copy. If an iteration fails verification,
            # we roll back to the unmodified structural state of our verified trains.
            test_courses = copy.deepcopy(active_roster)

            # --- Step 2: Calculate Rolling Stock Shunting Connections ---
            # Execute the optimization matchmaking rules to interconnect these target trains.
            # (Warning: This step maps localized platform arrivals to corresponding next departures)
            test_courses, test_connections = calculate_rolling_stock_connections(test_courses, all_infra_journeys,
                                                                                 platform_list)

            # --- Step 3: Directional Conflict and Feasibility Validation ---
            # Pass the integrated trajectories through the strict operational feasibility layer
            # to catch mixed-directional gridlocks, double head-ons, or loop deadlocks.
            safe_courses = filter_directional_conflicts(test_courses, all_infra_journeys, target_number=N_AGENTS_TARGET)

            # --- Step 4: Compliance Evaluation ---
            if len(safe_courses) == N_AGENTS_TARGET:
                # Convergence complete: All target trains are safely scheduled with compliant connections
                print(f"\n[SUCCESS] Iterative process complete! Found a (spatial) conflict-free roster on attempt {attempt}.")
                final_valid_courses = safe_courses
                final_valid_connections = test_connections
                break
            else:
                # Validation failure: Track allocations introduced operational infeasibilities.
                lost_count = N_AGENTS_TARGET - len(safe_courses)
                print(
                    f"[REJECTION SAMPLING] Connection layer introduced structural conflicts. Dropped {lost_count} unfeasible trains.")

                # Isolate the operational identifiers of the cleared safe course
                safe_ids = [c['course_id'] for c in safe_courses]

                # Roll back and retain only the original, unmodified states of the safe courses for the next pass
                active_roster = [c for c in active_roster if c['course_id'] in safe_ids]

                # --- Step 5: Replenish Active Roster from Reserves ---
                # Extract clean candidate courses from the standby reserve pool to replenish the active fleet
                if len(reserve_pool) >= lost_count:
                    print(
                        f"                     Drafting {lost_count} pristine candidate courses from the reserve pool roster...")
                    new_recruits = reserve_pool[:lost_count]
                    reserve_pool = reserve_pool[lost_count:]  # Evict drafted candidates from the standby pool array
                    active_roster.extend(new_recruits)  # Integrate new recruits into the active working slice
                else:
                    print(f"\n[CRITICAL ERROR] Reserve pool exhausted. Cannot replenish the roster to reach {N_AGENTS_TARGET}. Aborting execution frame.")
                    break

            attempt += 1

        # ============================================================
        # 10. CLEANUP & SYNCHRONIZATION (CHRONOLOGICAL ID RE-MAPPING)
        # ============================================================
        print("\n---10. Synchronizing Final Data Structures ---")

        course_list = final_valid_courses
        rolling_stock_connections = final_valid_connections

        if len(course_list) != N_AGENTS_TARGET:
            print(f"\n[WARNING] Optimization pipeline terminated with {len(course_list)} active trains "
                  f"instead of the requested target bounds ({N_AGENTS_TARGET}).")

        # Enforce strict chronological ordering across the cleared course roster based on absolute departure time
        course_list.sort(key=lambda x: x['dep_time'])

        # --- STRUCTURAL HASH-DICTIONARY RE-MAPPING ---
        # Because rejection sampling picks arbitrary non-sequential rows from the initial 10x oversampled
        # reserve pool (e.g., keeping agent 4, dropping 5-10, keeping 11), we build a reference translation map.
        # This prevents ID collisions and formats operational variables into sequential order for RECIFE.
        id_mapping = {}
        final_agents = []

        # --- Step A: Re-assign Sequential Identifiers & Register Translation Bindings ---
        for i, course in enumerate(course_list):
            final_agents.append(course['agent_obj'])

            old_id = course['course_id']
            new_id = f"COURSE_AGENT_{i}_{course['service_type']}"

            # Assign the clean, sequential identifier to the core course data structure
            course['course_id'] = new_id

            # Populate the translation dictionary map (e.g., "COURSE_AGENT_82_LOCAL" -> "COURSE_AGENT_0_LOCAL")
            id_mapping[old_id] = new_id

        # --- Step B: Safely Cascade Transformed Reference Keys Through Connection Links ---
        for conn in rolling_stock_connections:
            if conn['arr_course'] in id_mapping:
                conn['arr_course'] = id_mapping[conn['arr_course']]
            if conn['dep_course'] in id_mapping:
                conn['dep_course'] = id_mapping[conn['dep_course']]

        # Overwrite the underlying simulator agent registry arrays with the finalized, sorted roster
        env.agents = final_agents

        print(f"[SUCCESS] Final roster cleanly synchronized: {len(env.agents)} active rolling stock agents. "
              f"Sequential index keys successfully compiled and applied chronologically.")

        # ============================================================
        # 11. XML GENERATION (OPERATIONAL TIMETABLE LAYER)
        # ============================================================
        print("\n" + "=" * 75)
        print(f"{'--- 11. GENERATING RECIFE TIMETABLE XML ---':^75}")
        print("=" * 75)

        # Instantiate the root structural elements for the commercial scheduling schema
        root_tt, tt_def = generate_timetable_xml()

        # --- Step A: Define Course Type Speed Classes ---
        # Serializes structural thresholds separating Express and Local technical performance properties
        generate_coursetypes_xml(tt_def)

        # --- Step B: Serialize Commercial Train Courses ---
        # Maps chronologically ordered courses, absolute departure/arrival windows, and paths
        generate_courses_xml(tt_def, course_list, all_infra_journeys)

        # --- Step C: Append Rolling Stock Shunting Links ---
        # Establishes rolling stock connections between courses
        generate_connections_xml(tt_def, rolling_stock_connections)

        # ============================================================
        # 12. PHYSICAL TIMETABLE EXPORT
        # ============================================================
        print("\n--- 12. Exporting Operational Timetable XML File ---")
        tt_filename = os.path.join(INPUT_DIR, "real_TimeTable.xml")

        # Commit structured operational scheduling data directly to the local directory tree
        save_timetable_xml(root_tt, tt_filename)

        print(f"[SUCCESS] Timetable saved as '{tt_filename}'.")

        # ============================================================
        # 13. PERTURBATION GENERATION (STOCHASTIC STRESS TESTING LAYER)
        # ============================================================
        print("\n" + "=" * 75)
        print(f"{'--- 13. GENERATING PERTURBATION SCENARIO ---':^75}")
        print("=" * 75)

        # 1. Harvest all sequential course identifiers currently registered inside the active timetable
        all_course_ids = [c['course_id'] for c in course_list]

        # 2. Establish standardized file paths within the inputData directory branch
        pert_filename = os.path.join(INPUT_DIR, "real_Perturbation.xml")

        # 3. Generate the stochastically distributed operational delay scenario.
        # PERTURBATION_FRACTION of courses is given an entrance delay randomly pick from a uniformly distributed interval (PERTURBATION_RANGE)
        delays = generate_random_scenario(
            filename=pert_filename,
            scenario_name=f"Perturb_{INSTANCE_SEED:03d}",
            agent_ids=all_course_ids,
            delay_range=PERTURBATION_RANGE,
            fraction=PERTURBATION_FRACTION
        )

        print(f"[SUCCESS] Perturbation file saved as '{pert_filename}'.")
        print(
            f"          Scenario Parameters: {int(PERTURBATION_FRACTION * 100)}% of operational fleet injected with delays bounded between "
            f"{int(PERTURBATION_RANGE[0] / 60)} and {int(PERTURBATION_RANGE[1] / 60)} minutes.")

        # Final overall success message
    print("\n" + "=" * 75)
    print(f"{'PIPELINE EXECUTION COMPLETED SUCCESSFULLY':^75}")
    print("=" * 75)
