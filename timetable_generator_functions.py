"""
RECIFE-MILP Timetable and Operational Layer Generator Module
-----------------------------------------------------------
This module encapsulates core scheduling utilities, rolling stock shunting
matchmakers, and operational feasibility layers designed to interface
microscopic train trajectories with the RECIFE-MILP optimization solver.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time

def generate_timetable_xml(timetable_id="TT_Flatland_Gen_01", name="Flatland_Generated_Timetable"):
    """
    Initializes the root structure and definition container for the RECIFE Timetable XML document.

    Establishes a synchronized 24-hour operational scheduling window required
    as a baseline template boundary by the RECIFE optimization solver.

    Args:
        timetable_id (str): Unique identifier for the timetable instance database row.
        name (str): Meta name string for log identification.

    Returns:
        tuple: (root, tt_def) containing the root XML element and the timetable container element.
    """
    root = ET.Element("recifeObjects")

    # Define the core structural Timetable Container
    tt_def = ET.SubElement(root, "timetableDefinition", timetable_Id=timetable_id)
    ET.SubElement(tt_def, "name").text = name
    ET.SubElement(tt_def, "description").text = "Automated timetable export from Flatland SparseRailGenerator"

    # --- Dynamic Date Matrix Bounds Generation ---
    # RECIFE requires valid chronological calendar windows. We map an exact 24-hour horizon.
    current_date = datetime.now()
    end_date = current_date + timedelta(days=1)

    start_str = current_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    ET.SubElement(tt_def, "startDate").text = start_str
    ET.SubElement(tt_def, "endDate").text = end_str

    print(f"--- [SUCCESS] Timetable container '{timetable_id}' initialized ({start_str} to {end_str}) ---")
    return root, tt_def

def save_timetable_xml(root_element, output_filename):
    """
    Serializes the generated operational Timetable XML tree directly to disk.

    Handles pretty-printing indentation schema scaling and forces strict UTF-8
    encoding declarations required for robust parser interface compliance.

    Args:
        root_element (xml.etree.ElementTree.Element): The completed root 'recifeObjects' node tree.
        output_filename (str): Target physical destination file path on disk.
    """
    tree = ET.ElementTree(root_element)

    try:
        ET.indent(tree, space="  ", level=0)
    except AttributeError:
        pass

    tree.write(output_filename, encoding="utf-8", xml_declaration=True)
    print(f"--- [SUCCESS] Timetable successfully saved as '{output_filename}' ---")

def generate_coursetypes_xml(tt_def):
    """
    Generates the course types (train categories) for the RECIFE timetable.

    A Course Type defines the priority and optimization rules for specific
    groups of trains (e.g., Passenger, Freight, High-Speed). This function
    initializes a baseline passenger train type ('CL').

    Args:
        tt_def (xml.etree.ElementTree.Element): The timetableDefinition XML container.

    Returns:
        None (Modifies the tt_def XML tree in-place).
    """
    course_types_container = ET.SubElement(tt_def, "courseTypes")

    # Instantiate the global uniform rolling stock baseline class ('CL')
    for ct_id in ["CL"]:
        ct = ET.SubElement(course_types_container, "courseType", courseType_Id=ct_id)
        ET.SubElement(ct, "inObjFunc").text = "true"
        ET.SubElement(ct, "priorityFactor").text = "1"

    print("--- [SUCCESS] CourseTypes ('CL') added to the timetable. ---")

def generate_courses_xml(tt_def, course_list, all_infra_journeys):
    """
    Generates the RECIFE 'courses' (train schedules) based on the matched course list.

    A 'course' binds a specific train to a physical journey, defines its entrance/exit
    times into the simulation, assigns alternative routing options for the solver,
    and schedules its station stops.

    Args:
        tt_def (xml.etree.ElementTree.Element): The timetableDefinition XML container.
        course_list (list of dict): The list of courses, updated by the Matchmaker algorithm.
        all_infra_journeys (dict): Dictionary of all generated A* journeys.

    Returns:
        None (Modifies the tt_def XML tree in-place).
    """
    courses_container = ET.SubElement(tt_def, "courses")
    dwell_time = 30  # Standard dwell time at platforms in seconds

    # Dictionary to keep track of the number of agents departing from each city
    # Used to generate clean, sequential Train names
    city_counters = {}

    for course_data in course_list:
        start_sp = course_data['start_platform']
        end_sp = course_data['end_platform']
        course_id = course_data['course_id']  # Must exactly match the ID used in connections XML
        start_dir = course_data['agent_obj'].initial_direction

        # --- 1. Chronological Train Nomenclature Compilation ---
        city_num = course_data['start_city'].replace('C', '')  # Extracts '0' from 'C0'
        city_counters[city_num] = city_counters.get(city_num, 0) + 1
        local_train_num = city_counters[city_num]

        # --- 2. Build the Base Course XML ---
        course = ET.SubElement(courses_container, "course", course_Id=course_id)
        ET.SubElement(course, "name").text = f"Train_{course_data['start_city']}_{local_train_num}"
        ET.SubElement(course, "courseType_RefId").text = "CL"

        repeat = ET.SubElement(course, "repeatEvery")
        ET.SubElement(repeat, "weekday").text = "Everyday"

        # --- 3. Format Entrance and Exit Times ---
        # Convert absolute seconds (e.g., 28800) to HH:MM:SS format (e.g., 08:00:00)
        entry_time_str = time.strftime('%H:%M:%S', time.gmtime(course_data['dep_time']))
        arrival_time_str = time.strftime('%H:%M:%S', time.gmtime(course_data['arr_time']))

        entrance_time_el = ET.SubElement(course, "entranceTime")
        ET.SubElement(entrance_time_el, "day").text = "0"
        ET.SubElement(entrance_time_el, "time").text = entry_time_str

        exit_time_el = ET.SubElement(course, "exitTime")
        ET.SubElement(exit_time_el, "day").text = "0"
        ET.SubElement(exit_time_el, "time").text = arrival_time_str

        # --- 4. Primary Microscopic Path Integrity Mapping ---
        service_suffix = course_data.get('service_type', '')
        original_dir = course_data['agent_obj'].initial_direction

        # Target verification check on the native initial heading assignment
        expected_original_prefix = f"J_{start_sp}_TO_{end_sp}_DIR_{original_dir}"
        original_candidates = [j_id for j_id in all_infra_journeys.keys() if j_id.startswith(expected_original_prefix)]

        if original_candidates:
            original_candidates.sort()
            primary_journey_id = original_candidates[0]
            start_dir = original_dir
        else:
            # Fallback pathing recovery layer to prevent solver scheduling crashes if original vector failed pruning
            possible_candidates = []
            for d in range(4):
                prefix = f"J_{start_sp}_TO_{end_sp}_DIR_{d}"
                possible_candidates.extend([(j_id, d) for j_id in all_infra_journeys.keys() if j_id.startswith(prefix)])

            if not possible_candidates:
                print(
                    f"[WARNING] No structural journey discovered for {start_sp} -> {end_sp} across any heading. Bypassing course.")
                continue

            possible_candidates.sort(key=lambda x: x[0])
            primary_journey_id, start_dir = possible_candidates[0]
            print(
                f"[DIRECTION SWAP] Train {course_id} flipped to DIR_{start_dir} (Flatland's DIR_{original_dir} was too long or impossible).")

        # Determine the city template for alternatives (Crucial to prevent C++ memory crashes!)
        primary_stops = all_infra_journeys[primary_journey_id].get('local_stop_platforms', [])
        primary_cities = [sp.split('_')[1] for sp in primary_stops]

        ET.SubElement(course, "defJourneyInstance_RefId").text = f"{primary_journey_id}_{service_suffix}___CL"

        # --- 5. Alternative Destination Routing Allocation ---
        end_city_code = end_sp.split('_')[1]
        alt_start_prefix = f"J_{start_sp}_TO_SP_{end_city_code}_"
        alt_dir_match = f"_DIR_{start_dir}_"

        alternative_journeys = []
        for j_id in all_infra_journeys.keys():
            if j_id.startswith(alt_start_prefix) and alt_dir_match in j_id:
                if j_id != primary_journey_id:
                    # Intermediate Station Node Boundary Check to guarantee topological sequence compliance
                    if service_suffix == "LOCAL":
                        alt_stops = all_infra_journeys[j_id].get('local_stop_platforms', [])
                        alt_cities = [sp.split('_')[1] for sp in alt_stops]

                        if primary_cities != alt_cities:
                            continue  # Reject alternative paths crossing a conflicting station profile

                    alternative_journeys.append(j_id)

        if alternative_journeys:
            alt_container = ET.SubElement(course, "alternativeJourneys")
            alternative_journeys.sort()
            for a_id in alternative_journeys:
                ET.SubElement(alt_container, "altJourneyInstance_RefId").text = f"{a_id}_{service_suffix}___CL"

        # --- 6. Stop Specifications ---
        stops_spec = ET.SubElement(course, "stopsSpecifications")
        current_stop_idx = 0

        # --- STATION BOUNDARY 1: Origin Point ---
        stop_start = ET.SubElement(stops_spec, "stopSpecification", StoSeqElmt_RefIdx=str(current_stop_idx))
        arr_start = ET.SubElement(stop_start, "scheduledArrivalTime")
        ET.SubElement(arr_start, "day").text = "0"
        ET.SubElement(arr_start, "time").text = entry_time_str

        dep_start = ET.SubElement(stop_start, "scheduledDepartureTime")
        ET.SubElement(dep_start, "day").text = "0"
        dep_time_sec = course_data['dep_time'] + dwell_time
        ET.SubElement(dep_start, "time").text = time.strftime('%H:%M:%S', time.gmtime(dep_time_sec))

        ET.SubElement(stop_start, "minimumDwellTime").text = str(dwell_time)
        ET.SubElement(stop_start, "optionalStop").text = "false"
        current_stop_idx += 1

        # --- STATION BOUNDARY 2: Intermediate Station Matrices ---
        rel_times = []
        if service_suffix == "LOCAL":
            rel_times = all_infra_journeys[primary_journey_id].get('stops_relative_times_LOCAL', [])

        for rel_time in rel_times:
            accumulated_dwell_penalty = current_stop_idx * dwell_time
            inter_time_sec = int(course_data['dep_time'] + rel_time + accumulated_dwell_penalty)
            inter_time_str = time.strftime('%H:%M:%S', time.gmtime(inter_time_sec))

            stop_inter = ET.SubElement(stops_spec, "stopSpecification", StoSeqElmt_RefIdx=str(current_stop_idx))
            arr_inter = ET.SubElement(stop_inter, "scheduledArrivalTime")
            ET.SubElement(arr_inter, "day").text = "0"
            ET.SubElement(arr_inter, "time").text = inter_time_str

            dep_inter = ET.SubElement(stop_inter, "scheduledDepartureTime")
            ET.SubElement(dep_inter, "day").text = "0"
            ET.SubElement(dep_inter, "time").text = time.strftime('%H:%M:%S', time.gmtime(inter_time_sec + dwell_time))

            ET.SubElement(stop_inter, "minimumDwellTime").text = str(dwell_time)
            ET.SubElement(stop_inter, "optionalStop").text = "false"
            current_stop_idx += 1

        # --- STATION BOUNDARY 3: Final Destination Terminal ---
        stop_end = ET.SubElement(stops_spec, "stopSpecification", StoSeqElmt_RefIdx=str(current_stop_idx))
        arr_end = ET.SubElement(stop_end, "scheduledArrivalTime")
        ET.SubElement(arr_end, "day").text = "0"
        ET.SubElement(arr_end, "time").text = arrival_time_str

        ET.SubElement(stop_end, "minimumDwellTime").text = "0"
        ET.SubElement(stop_end, "optionalStop").text = "false"

def get_directed_edges(path_with_tds):
    """
    Deconstructs a comprehensive trajectory path array into a unique set of directed
    TDS transition edges (TDS_A -> TDS_B).

    This utility functions as a structural pre-processing step for macro-routing conflict
    and loop deadlock filters. It compresses raw cell-by-cell path configurations into a
    clean topological sequence of consecutive tracking blocks—collapsing duplicate adjacent
    identifiers caused by multi-cell track sections—and extracts directed vector movements.

    Args:
        path_with_tds (list): A sequence of structural micro-routing path tuples formatted as:
                              [((row, col), tds_id), ...].

    Returns:
        set: A unique hash-set collection containing directed spatial tracking edges:
             {('TDS_A', 'TDS_B'), ('TDS_B', 'TDS_C'), ...}.
    """
    edges = set()

    # --- Step 1: Deduplicate Consecutive Section Allocations ---
    # Extract the raw structural timeline of TDS identifiers, collapsing sequential
    # duplicate tracking frames to establish a clean node-to-node network grid line.
    tds_sequence = []
    for _, tds_id in path_with_tds:
        if not tds_sequence or tds_sequence[-1] != tds_id:
            tds_sequence.append(tds_id)

    # --- Step 2: Construct Directed Topology Vector Edges ---
    # Intertwine the compressed timeline nodes to extract directed infrastructure vector edges.
    for i in range(len(tds_sequence) - 1):
        tds1 = tds_sequence[i]
        tds2 = tds_sequence[i + 1]

        # Committing transitions to a hash-set automatically discards overlapping route segments
        edges.add((tds1, tds2))

    return edges

def filter_directional_conflicts(course_list, all_infra_journeys, target_number=40):
    """
    Filters out operationally unfeasible train courses to guarantee RECIFE-MILP stability.

    This rejection sampling filter processes candidate schedules to eliminate intersecting
    trajectories that violate macro-routing constraints, preventing severe optimization
    infeasibilities (such as mixed direction locking, multiple opposing head-ons,
    and circular sequence deadlocks) within the mathematical MILP solver core.

    Args:
        course_list (list): Initial pool of candidate train courses generated by Flatland.
        all_infra_journeys (dict): Routing database containing pre-calculated path and TDS information.
        target_number (int): The exact target quantity of conflict-free courses needed for the instance.

    Returns:
        list: A strictly filtered roster of completely feasible, conflict-free courses.
    """
    print("\n" + "=" * 60)
    print(f"--- Running Strict Feasibility Filter (Target: {target_number} trains) ---")

    safe_courses = []

    for course in course_list:
        journey_id = course['journey_id']
        if journey_id not in all_infra_journeys:
            continue

        # Extract structural timeline maps and edge allocations for Course A
        path_A_full = [p[1] for p in all_infra_journeys[journey_id]['path_with_tds']]
        edges_A = get_directed_edges(all_infra_journeys[journey_id]['path_with_tds'])
        tds_set_A = set(path_A_full)
        has_conflict = False

        # Evaluate candidate course against the structurally cleared safe roster
        for safe_course in safe_courses:
            safe_journey_id = safe_course['journey_id']
            path_B_full = [p[1] for p in all_infra_journeys[safe_journey_id]['path_with_tds']]
            edges_B = get_directed_edges(all_infra_journeys[safe_journey_id]['path_with_tds'])
            tds_set_B = set(path_B_full)

            # Isolate shared infrastructure elements using hash-set intersection
            common_tds = tds_set_A.intersection(tds_set_B)
            if not common_tds:
                continue

            # --- 1. Isolate Encounter Blocks (Sorted chronologically by Course A's timeline) ---
            common_tds_sorted_A = sorted(list(common_tds), key=lambda x: path_A_full.index(x))

            encounter_blocks = []
            if common_tds_sorted_A:
                current_block = [common_tds_sorted_A[0]]
                for i in range(1, len(common_tds_sorted_A)):
                    idx_prev = path_A_full.index(common_tds_sorted_A[i - 1])
                    idx_curr = path_A_full.index(common_tds_sorted_A[i])
                    if idx_curr == idx_prev + 1:
                        current_block.append(common_tds_sorted_A[i])
                    else:
                        encounter_blocks.append(current_block)
                        current_block = [common_tds_sorted_A[i]]
                encounter_blocks.append(current_block)

            # --- 2. Sequence Consistency Check (Circular Deadlock Loop Rule) ---
            # Track index boundaries where each shared encounter block initiates inside Course B
            block_indices_in_B = []
            for block in encounter_blocks:
                idx_in_B = path_B_full.index(block[0])
                block_indices_in_B.append(idx_in_B)

            # If the entry order of these blocks inside Course B is not strictly sequential
            # (neither strictly increasing nor decreasing), the trains cross each other's
            # paths in a circular loop. This creates a spatial deadlock that makes
            # the MILP sequencing constraints mathematically unfeasible for the solver.
            if len(block_indices_in_B) > 1:
                is_consistent = all(block_indices_in_B[i] < block_indices_in_B[i + 1]
                                    for i in range(len(block_indices_in_B) - 1))
                is_reverse_consistent = all(block_indices_in_B[i] > block_indices_in_B[i + 1]
                                            for i in range(len(block_indices_in_B) - 1))

                if not (is_consistent or is_reverse_consistent):
                    print(f"[LOOP DEADLOCK] {course['course_id']} vs {safe_course['course_id']}. "
                          f"Sequence crossover in B: {block_indices_in_B}. Dropping candidate...")
                    has_conflict = True
                    break

            # --- 3. Analyze Directional Trajectories Per Block ---
            same_dir_count = 0
            opp_encounters = 0
            has_single_tds_block = False

            for block in encounter_blocks:
                if len(block) == 1:
                    has_single_tds_block = True

                tds_id = block[0]
                edge_A = [e for e in edges_A if e[0] == tds_id]
                edge_B = [e for e in edges_B if e[0] == tds_id]
                is_terminal_B = False

                if not edge_B:
                    edge_B = [e for e in edges_B if e[1] == tds_id]
                    is_terminal_B = True

                if edge_A and edge_B:
                    eA = edge_A[0]  # Format mapping: (TDS_current, TDS_next)
                    eB = edge_B[0]  # Format mapping: (TDS_current, TDS_next) OR (TDS_prev, TDS_current)

                    if not is_terminal_B:
                        # Nominal execution case: Both trajectories exit this block segment
                        if eA[1] == eB[1]:
                            same_dir_count += 1  # Standard following movement pattern
                        else:
                            if (eA[1], eA[0]) in edges_B:
                                opp_encounters += 1  # Opposing head-on trajectory discovered
                    else:
                        # Terminal execution case: Course B terminates operations inside this block segment
                        if eA[1] == eB[0]:
                            opp_encounters += 1  # Opposing entry trajectory conflict
                        elif (eB[0], eB[1]) == (eA[0], eA[1]):
                            same_dir_count += 1

            # --- 4. Evaluate Safety Compliance Rules ---

            # Constraint 1: Mixed Direction Locking
            if same_dir_count > 0 and opp_encounters > 0:
                print(
                    f"[INFEASIBLE] Mixed directional locks: {course['course_id']} vs {safe_course['course_id']}. Dropping candidate...")
                has_conflict = True
                break

            # Constraint 2: Multiple Intersecting Head-Ons
            if opp_encounters > 1:
                print(
                    f"[STRUCTURAL CONFLICT] Multiple head-on encounters ({opp_encounters} blocks) between {course['course_id']} vs {safe_course['course_id']}. Dropping candidate...")
                has_conflict = True
                break

            # Constraint 3: Single TDS Ambiguity Combined with Multi-segment Intersections
            if len(encounter_blocks) > 1 and has_single_tds_block:
                print(
                    f"[AMBIGUOUS TOPOLOGY] Multiple segments with single-block overlap: {course['course_id']} vs {safe_course['course_id']}. Dropping candidate...")
                has_conflict = True
                break

        if not has_conflict:
            safe_courses.append(course)
            if len(safe_courses) == target_number:
                break

    return safe_courses

def calculate_rolling_stock_connections(course_list, all_infra_journeys, platform_list):
    """
    Matches arriving and departing train courses within a shared city node to optimize fleet shunting loops.

    Processes circulation profiles using a strict FIFO queue tracking strategy. Integrates
    turnaround windows (>= 120s), validates micro-routing path options, and evaluates local
    track segment capacities using a dynamic sweep-line event model to actively prevent operational
    terminal station gridlocks.

    Args:
        course_list (list of dict): Pool roster of scheduled train courses across the instance.
        all_infra_journeys (dict): Pre-calculated microscopic routing database.
        platform_list (list): Structural dataset of pre-mapped platform boundaries.

    Returns:
        tuple: (course_list, connections_data) containing the updated course profiles
               and the generated turnaround linkage metadata.
    """
    connections_data = []
    rejected_by_capacity = 0

    # --- Phase 1: Compile Maximum Structural Platform Metrics ---
    city_capacities = {}
    for _, p_id in platform_list:
        # Isolate city identifier strings (e.g., extracting 'C1' from 'SP_C1_P0_6_4')
        city = p_id.split('_')[1]
        city_capacities[city] = city_capacities.get(city, 0) + 1

    # --- Phase 2: Trace Unique City Operational Nodes ---
    cities = set([c['start_city'] for c in course_list] + [c['end_city'] for c in course_list])

    for city in cities:
        # Buffer Safety Margin: Always reserve exactly one platform slot to absorb non-shunting
        # express trains and prevent upstream choke points outside station interlocking lines.
        physical_platforms = city_capacities.get(city, 99)
        max_allowed_capacity = physical_platforms - 1 if physical_platforms > 1 else 1

        active_layovers = []

        # Isolate and sort inbound vectors (First-In, First-Out alignment)
        arrivals = [c for c in course_list if c['end_city'] == city]
        arrivals.sort(key=lambda x: x['arr_time'])

        # Isolate and sort outbound vectors chronologically
        departures = [c for c in course_list if c['start_city'] == city]
        departures.sort(key=lambda x: x['dep_time'])

        # --- Phase 3: Rolling Stock Search & Capacity Verification Loops ---
        for arr_course in arrivals:
            arr_time = arr_course['arr_time']
            arr_platform = arr_course['end_platform']
            matched_dep_course = None

            for dep_course in departures:
                # Operational Metric 1: Fleet Turnaround Buffer (Minimum 120 seconds required)
                if dep_course['dep_time'] >= arr_time + 120:

                    # Operational Metric 2: Trace Microscopic Path Layout Connectivity
                    target_dest_platform = dep_course['end_platform']
                    required_dir = dep_course['agent_obj'].initial_direction
                    expected_journey_prefix = f"J_{arr_platform}_TO_{target_dest_platform}_DIR_{required_dir}_"

                    has_valid_route = any(
                        j_id.startswith(expected_journey_prefix) for j_id in all_infra_journeys.keys())

                    if has_valid_route:
                        # Operational Metric 3: Station Capacity Check
                        test_interval = (arr_time, dep_course['dep_time'])
                        all_intervals = active_layovers + [test_interval]

                        # Populate discrete delta events (+1 on arrival step, -1 on departure step)
                        events = []
                        for start_t, end_t in all_intervals:
                            events.append((start_t, 1))
                            events.append((end_t, -1))

                        # Chronological sorting: Process departure drops (-1) prior to arrivals (+1) to clear bounds
                        events.sort(key=lambda x: (x[0], x[1]))

                        max_occupancy = 0
                        current_occupancy = 0

                        for t, change in events:
                            current_occupancy += change
                            if current_occupancy > max_occupancy:
                                max_occupancy = current_occupancy

                        if max_occupancy <= max_allowed_capacity:
                            # Station platform capacity bounds validated for this layover frame
                            matched_dep_course = dep_course
                            break  # Terminate search branch; match confirmed
                        else:
                            # If the earliest valid departure overloads the station, a later departure
                            # will only extend the layover and make the overlap worse.
                            # We abort connecting this specific arrival to save the station.
                            rejected_by_capacity += 1
                            print(
                                f"[STATION OVERFLOW PREVENTED] Station {city} is full. Train arriving at {arr_time} will not be connected.")
                            break

            # --- Phase 4: Execute Structural Overwrites & Cascade Data ---
            if matched_dep_course:
                # Re-anchor the departure course platform coordinate to match the arrival terminal slot
                matched_dep_course['start_platform'] = arr_platform

                req_dir = matched_dep_course['agent_obj'].initial_direction
                target_dest = matched_dep_course['end_platform']

                # Construct the comprehensive target alternative baseline key signature
                exact_new_journey_key = f"J_{arr_platform}_TO_{target_dest}_DIR_{req_dir}_ALT_0"

                if exact_new_journey_key in all_infra_journeys:
                    matched_dep_course['journey_id'] = exact_new_journey_key
                else:
                    # Fallback assignment: Match the first available alternate route meeting directional heading rules
                    prefix_with_dir = f"J_{arr_platform}_TO_{target_dest}_DIR_{req_dir}_"
                    fallback_key = next((j_id for j_id in all_infra_journeys.keys()
                                         if j_id.startswith(prefix_with_dir)), None)

                    if fallback_key:
                        matched_dep_course['journey_id'] = fallback_key
                    else:
                        print(f"[ROUTING ERROR] No valid path found in direction vector DIR_{req_dir} from "
                              f"platform {arr_platform}. Match invalidated.")
                        matched_dep_course = None
                        continue

                # Lock the validated interval window to monitor future scheduling iterations
                active_layovers.append((arr_time, matched_dep_course['dep_time']))

                # Format and append turnaround data for RECIFE XML serialization
                connections_data.append({
                    'arr_course': arr_course['course_id'],
                    'dep_course': matched_dep_course['course_id'],
                    'station': city,
                    'min_dur': 120,
                    'max_tol': 86400  # 24-hour maximum turnaround tolerance profile
                })

                # Evict the matched departure option from the active pool to prevent double-booking anomalies
                departures.remove(matched_dep_course)
    print(f"MATCHMAKER_STATS: Made {len(connections_data)}, Rejected {rejected_by_capacity}")
    print(f"--- [SUCCESS] Matchmaker created {len(connections_data)} capacity-checked Rolling Stock Connections. ---")
    return course_list, connections_data

def generate_connections_xml(tt_def, connections_list):
    """
    Serializes structural turnaround connection links into the RECIFE Timetable XML layout tree.

    Enforces fleet resource dependency linkages and physical rolling stock circulation
    (turnarounds) across subsequent course profiles at designated terminal station groups.

    Args:
        tt_def (xml.etree.ElementTree.Element): The target timetableDefinition XML container node.
        connections_list (list of dict): Collection of connection datasets processed by the Matchmaker.
    """
    # If the matchmaker evaluation yielded zero valid turnarounds, bypass the XML block generation
    if not connections_list:
        print("--- [INFO] No operational rolling stock connections available to generate. ---")
        return

    # Create the root structural sub-container for the connection layer
    connections_container = ET.SubElement(tt_def, "connections")

    for conn in connections_list:
        arr_id = conn['arr_course']
        dep_id = conn['dep_course']
        conn_id = f"{arr_id}_{dep_id}"

        # In 'generate_stopping_groups_xml', terminal facilities are registered as 'Station_City_0', 'Station_City_1', etc.
        # Cleanse and extract the raw index value from the Matchmaker city key string (e.g., transforming 'C1' to '1')
        city_num = conn['station'].replace('C', '')
        station_ref_id = f"Station_City_{city_num}"

        # Initialize the XML node object for an individual turnaround dependency link
        connection_el = ET.SubElement(connections_container, "connection", connection_Id=conn_id)

        # Map structural reference bindings linking the inbound course directly to the outbound mission profile
        ET.SubElement(connection_el, "arrivingCourse_RefId").text = conn['arr_course']
        ET.SubElement(connection_el, "departingCourse_RefId").text = conn['dep_course']

        # Apply temporal boundaries (configured in absolute seconds)
        # Minimum time threshold required for commercial passenger exchange and locomotive cabin swap maneuvers
        ET.SubElement(connection_el, "minimumDuration").text = str(conn['min_dur'])

        # Maximum permitted layover window tolerance before the equipment circulation link is invalidated
        ET.SubElement(connection_el, "maximumTolerance").text = str(conn['max_tol'])

        # Explicitly assign the commercial station group node where the shunting balancing occurs
        ET.SubElement(connection_el, "atStoGro_refId").text = station_ref_id

        ET.SubElement(connection_el, "connectionType").text = "RollingStock-Balance"

    print(f"--- [SUCCESS] Generated {len(connections_list)} <connection> elements in the XML. ---")