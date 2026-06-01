"""
RECIFE-MILP Compliant Custom Line Generator Module
==================================================

Provenance & Modification Register
----------------------------------
* Origin:
  This module is adapted from the official Flatland-RL toolkit repository
  (flatland/envs/line_generators.py), authored by the Flatland Association.

* This script was decoupled from the global library space and refactored into a local,
  reproducible project module. The core 'CustomSparseLineGen' class was modified to match
  the operational flow of agents with the asymmetric capacity of the generated cities.

Key Algorithmic Adjustments:
1. Capacity-Weighted Origin-Destination Selection:
   Introduced a stochastic probability array (`city_probabilities`) computed dynamically from
   the number of platforms inside each urban cluster (`hints['train_stations']`). This shifts
   the generation from a uniform distribution to a capacity-proportional assignment.
"""

from typing import Tuple, List, Callable, Mapping, Optional, Any, Union
import numpy as np
from numpy.random.mtrand import RandomState

# --- Flatland Core Imports ---
from flatland.core.grid.grid4 import Grid4TransitionsEnum
from flatland.core.grid.grid_utils import IntVector2DArray
from flatland.envs.rail_grid_transition_map import RailGridTransitionMap
from flatland.envs.rail_trainrun_data_structures import Waypoint
from flatland.envs.timetable_utils import Line

# Re-use standard Flatland abstractions to minimize codebase redundancy and maintain compliance
from flatland.envs.line_generators import BaseLineGen, speed_initialization_helper, LineGenerator


def custom_sparse_line_generator(speed_ratio_map: Mapping[float, float] = None, seed: int = 1,
                                 line_length: int = 2) -> LineGenerator:
    return CustomSparseLineGen(speed_ratio_map, seed, line_length)


class CustomSparseLineGen(BaseLineGen):
    def __init__(self, speed_ratio_map: Mapping[float, float] = None, seed: int = 1, line_length: int = 2):
        super().__init__(speed_ratio_map, seed, line_length)

    @staticmethod
    def decide_orientation(rail, start, target, possible_orientations, np_random: RandomState) -> int:
        feasible_orientations = []
        for orientation in possible_orientations:
            if rail.check_path_exists(start[0], orientation, target[0]):
                feasible_orientations.append(orientation)
        if len(feasible_orientations) > 0:
            return np_random.choice(feasible_orientations)
        else:
            return 0

    def _assign_station_in_start_and_target_city(self, hints: dict, rail: RailGridTransitionMap, city_start: int,
                                                 city_target: int,
                                                 np_random: RandomState):
        train_stations = hints['train_stations']
        city_orientation = hints['city_orientations']
        city_start_num_stations = len(train_stations[city_start])
        city_target_num_stations = len(train_stations[city_target])

        city_start_possible_orientations = [city_orientation[city_start],
                                            (city_orientation[city_start] + 2) % 4]

        agent_start_idx = np_random.randint(0, city_start_num_stations)
        agent_target_idx = np_random.randint(0, city_target_num_stations)

        agent_start = train_stations[city_start][agent_start_idx]
        agent_target = train_stations[city_target][agent_target_idx]

        agent_orientation = self.decide_orientation(
            rail, agent_start, agent_target, city_start_possible_orientations, np_random)

        return agent_start, agent_orientation, agent_target

    def generate(self, rail: RailGridTransitionMap, num_agents: int, hints: dict = None, num_resets: int = 0,
                 np_random: RandomState = None) -> Line:
        _runtime_seed = self.seed + num_resets
        city_positions: IntVector2DArray = hints['city_positions']

        # --- NIEUW: Bereken de kansen (gewichten) per stad op basis van aantal sporen ---
        train_stations = hints['train_stations']
        num_stations_per_city = [len(stations) for stations in train_stations]
        total_stations = sum(num_stations_per_city)

        if total_stations > 0:
            city_probabilities = [num / total_stations for num in num_stations_per_city]
        else:
            city_probabilities = None
        # ---------------------------------------------------------------------------------

        agent_positions = []
        agent_targets = []
        agent_directions = []

        for agent_idx in range(num_agents):
            if agent_idx % 2 == 0:
                # Inject the customized probability vector array directly into the sampling execution frame
                city_idx: List[int] = list(
                    np_random.choice(len(city_positions), self.line_length, replace=False, p=city_probabilities))
            else:
                city_idx = list(reversed(city_idx))

            cur_agent_orientations = []
            cur_agent_positions = []
            for city1, city2 in zip(city_idx, city_idx[1:]):
                cur_agent_start, cur_agent_orientation, cur_agent_target = self._assign_station_in_start_and_target_city(
                    hints, rail, city1, city2, np_random)
                cur_agent_positions.append((cur_agent_start[0][0], cur_agent_start[0][1]))
                cur_agent_orientations.append(Grid4TransitionsEnum(cur_agent_orientation))
            agent_positions.append(cur_agent_positions)
            agent_targets.append((cur_agent_target[0][0], cur_agent_target[0][1]))
            agent_directions.append(cur_agent_orientations)

        if self.speed_ratio_map:
            agent_speeds = speed_initialization_helper(num_agents, self.speed_ratio_map, np_random=np_random)
        else:
            agent_speeds = [1.0] * len(agent_positions)

        agent_positions = [[[p] for p in pa] for pa in agent_positions]
        agent_directions = [[[d] for d in da] for da in agent_directions]
        agent_waypoints = {i: [[Waypoint(fpa, fda) for fpa, fda in zip(pa, da)] for pa, da in zip(pas, das)] + [
            [Waypoint(target, None)]] for
                           i, (pas, das, target)
                           in enumerate(zip(agent_positions, agent_directions, agent_targets))}
        return Line(agent_waypoints=agent_waypoints, agent_speeds=agent_speeds)