"""
Flatland Environment Initialization Helper Module
=================================================

Provenance & Modification Register
----------------------------------
* Origin:
  This module is adapted from the 'flatland_railway_extension' library
  (FlatlandEnvironmentHelper.py) authored by Adrian Egli.
  Repository: https://github.com/aiAdrian/flatland_railway_extension.git

  Permission Notice: As required by the author, academic or commercial
  use of any concepts or code components from this toolkit requires
  explicit attribution to the original author.

* The class was refactored locally to integrate custom procedural
  generation extensions. It overrides the default uniform grid behavior
  by passing asynchronous city configuration arrays and binding a
  tailored scheduling line generator to ensure output compatibility
  with the downstream RECIFE-MILP optimization layer.

Key Algorithmic Adjustments:
1. Custom Structural Generator Hook:
   Swapped the native Flatland generator import for the customized local
   `custom_rail_generator` module, enabling asymmetrical platform counts
   per cluster via `city_track_counts`.
2. Capacity-Weighted Demand Line Generation:
   Replaced the uniform legacy line generator with a capacity-proportional
   traffic assignment tool (`custom_sparse_line_generator`). Train spawning
   probabilities are dynamically scaled against local track counts to mitigate
   artificial bottleneck choke points in minor stations.
3. Metric Validation Output:
   Added standard initialization prints (`GENERATOR_PARAMS`) to output execution
   metadata.
"""

import random
from typing import Union, Type
import numpy as np

# --- Flatland Core Imports ---
from flatland.core.env_observation_builder import ObservationBuilder
from flatland.envs.malfunction_generators import MalfunctionParameters, ParamMalfunctionGen
from flatland.envs.rail_env import RailEnv

# --- Custom Module & Extension Imports ---
from custom_rail_generator import sparse_rail_generator
from custom_line_generator import custom_sparse_line_generator
from flatland_railway_extension.utils.ShortestPathNextStepObservation import ShortestPathNextStepObservation

class FlatlandEnvironmentHelper:
    def __init__(self, rail_env: Type[RailEnv] = RailEnv,
                 grid_width=30, grid_height=40, number_of_agents=10, n_cities=3,
                 random_seed=0, obs_builder_object: Union[ObservationBuilder, None] = None,
                 city_track_counts: list = None):
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.number_of_agents = number_of_agents
        self.n_cities = n_cities
        self.city_track_counts = city_track_counts
        self._random_seed(random_seed)
        self._obs_builder_object = obs_builder_object
        self.env = self._create_flatland_env(rail_env)
        self.env.reset()

    def _random_seed(self, random_seed):
        self.random_seed = random_seed
        np.random.seed(self.random_seed)
        random.seed(self.random_seed)

    def _create_flatland_env(self, rail_env: Type[RailEnv],
                             max_rails_between_cities=2,
                             max_rails_in_city=1,
                             malfunction_rate=1 / 1000) -> RailEnv:
        # Display runtime instance configurations for pipeline tracking purposes        print(f"GENERATOR_PARAMS: max_between={max_rails_between_cities}, max_in={max_rails_in_city}")
        if self._obs_builder_object == None:
            self._obs_builder_object = ShortestPathNextStepObservation()

        return rail_env(
            width=self.grid_width,
            height=self.grid_height,
            rail_generator=sparse_rail_generator(
                max_num_cities=self.n_cities,
                seed=self.random_seed,
                grid_mode=None,
                max_rails_between_cities=max_rails_between_cities,
                max_rail_pairs_in_city=max_rails_in_city,
                city_track_counts=self.city_track_counts
            ),
            line_generator=custom_sparse_line_generator(
                seed=self.random_seed
            ),
            malfunction_generator=ParamMalfunctionGen(
                MalfunctionParameters(
                    malfunction_rate=malfunction_rate, min_duration=10, max_duration=50
                )
            ),
            random_seed=self.random_seed,
            number_of_agents=self.number_of_agents,
            obs_builder_object=self._obs_builder_object
        )

    def get_rail_env(self):

        return self.env

    def get_agent_position_and_direction(self, handle):
        '''
        Returns the agent position - if not yet started (active) it returns the initial position

        :param handle: agent reference (handle)

        :return: agent_pos, agent_dir, agent_state, agent_target, is_agent_off_map
        '''
        agent = self.env.agents[handle]
        agent_pos = agent.position
        agent_dir = agent.direction
        if agent_pos is None:
            agent_pos = agent.initial_position
            agent_dir = agent.initial_direction
        return agent_pos, agent_dir, agent.state, agent.target, agent.position is None
