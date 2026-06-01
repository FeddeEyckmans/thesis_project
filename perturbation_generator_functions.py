"""
RECIFE-MILP Perturbation and Delay Scenario Generator Module
------------------------------------------------------------
This module automates the generation of stochastic perturbation datasets
to stress-test timetable robustness and conduct sensitivity analysis
within the RECIFE-MILP optimization engine framework.
"""

import xml.etree.ElementTree as ET
import random

def generate_perturbation_xml(filename, scenario_name, delays):
    """
    Generates a compliant RECIFE perturbation XML file to inject operational train delays.

    Constructs the necessary XML schema definitions to evaluate timetable stability
    by introducing entry time disruptions to a specific subgroup of scheduled courses.

    Args:
        filename (str): The physical output file path (e.g., 'real_Perturbation.xml').
        scenario_name (str): The unique scenario identifier string used for logs and metadata.
        delays (dict or list): Collection of {course_id: delay_in_seconds} or a list
                               of tuples mapping disrupted entities to their deviation offsets.
    """
    root = ET.Element("recifeObjects", {
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:noNamespaceSchemaLocation": "all.xsd"
    })

    # --- Setup Scenario Container ---
    scenario_def = ET.SubElement(root, "PerturbationScenarioDefinition")
    ET.SubElement(scenario_def, "name").text = scenario_name
    ET.SubElement(scenario_def, "description").text = f"Automated operational stress-test scenario: {scenario_name}"

    pert_list = ET.SubElement(scenario_def, "perturbationsList")

    # Safely unpack both dictionary and list-of-tuples collection formats
    delay_items = delays.items() if isinstance(delays, dict) else delays

    # --- Serialize Perturbation Structural Nodes ---
    for course_id, delay_sec in delay_items:
        pert_id = f"{scenario_name}_agent_{course_id}"
        pert_node = ET.SubElement(pert_list, "perturbation", perturbation_Id=pert_id)

        # 'entranceDelayPert' injects primary deviation penalties right at the simulation entry gate boundary
        delay_node = ET.SubElement(pert_node, "entranceDelayPert")
        ET.SubElement(delay_node, "course_RefId").text = str(course_id)
        ET.SubElement(delay_node, "value").text = str(delay_sec)

    # --- Pretty-Print Indentation and Save XML Dataset ---
    tree = ET.ElementTree(root)

    try:
        ET.indent(tree, space="  ", level=0)
    except AttributeError:
        pass  # Silent fallback for older Python versions

    tree.write(filename, encoding="utf-8", xml_declaration=True)

    print(f"--- [SUCCESS] {filename} generated with {len(delay_items)} delayed courses ---")


def generate_random_scenario(filename, scenario_name, agent_ids, delay_range=(300, 900), fraction=0.2):
    """
    Executes a randomized rejection sampling method to generate stochastic delay scenarios.

    Randomly samples a defined fraction of the active fleet roster and injects
    a uniformly distributed entrance delay boundary across each selected entity.

    Args:
        filename (str): Target physical destination file path on disk.
        scenario_name (str): Unique scenario identifier string.
        agent_ids (list): List of clean, sequential course identifiers registered in the timetable.
        delay_range (tuple): The (minimum, maximum) delay bounds in seconds.
        fraction (float): Probability fraction representing the proportion of the fleet targeted for delay.

    Returns:
        dict: Look-up dataset mapping perturbed course identifiers to their absolute injected delay seconds.
    """
    # Calculate the total volume of courses to disrupt, enforcing a baseline minimum floor of 1
    num_delayed = max(1, int(len(agent_ids) * fraction))

    # Sample candidate operational courses stochastically from the active fleet pool
    delayed_agents = random.sample(agent_ids, num_delayed)
    delayed_agents.sort()

    # Allocate random timeline deviations uniformly distributed within the specified range boundaries
    delays = {agent: random.randint(delay_range[0], delay_range[1]) for agent in delayed_agents}

    # Pass the compiled stochastic data profile directly to the XML serialization layer
    generate_perturbation_xml(filename, scenario_name, delays)

    return delays