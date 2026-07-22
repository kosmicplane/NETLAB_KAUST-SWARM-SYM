"""PettingZoo-style parallel environment backed by NETLAB contracts.

The class intentionally has no hard dependency on PettingZoo. When PettingZoo
is installed it can be wrapped directly because reset() and step() follow the
Parallel API. Authoritative packet advancement remains outside this class.
"""
from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from .algorithm_contracts import AlgorithmAction, AlgorithmManifest
from .safety_shield import apply_safety_shield


@dataclass
class RewardWeights:
    formation: float = 1.0
    connectivity: float = 2.0
    service_continuity: float = 2.0
    packet_delivery: float = 1.5
    safety: float = 4.0
    energy: float = 0.25
    control_effort: float = 0.2
    age_of_information: float = 0.5


class NetlabParallelEnv:
    metadata = {"name": "netlab_snaas_parallel_v1", "is_parallelizable": True}

    def __init__(
        self,
        config: Mapping[str, Any],
        initial_observation: Mapping[str, Any],
        *,
        max_steps: int = 1000,
        reward_weights: Optional[RewardWeights] = None,
    ) -> None:
        self.config = copy.deepcopy(dict(config))
        self.initial_observation = copy.deepcopy(dict(initial_observation))
        self.max_steps = max(1, int(max_steps))
        self.weights = reward_weights or RewardWeights()
        self.possible_agents = [
            str(item.get("id"))
            for item in self.initial_observation.get("uavs", [])
            if isinstance(item, Mapping) and item.get("id") and item.get("active", True)
        ]
        self.agents = list(self.possible_agents)
        self._rng = random.Random(0)
        self._step_count = 0
        self._observation = copy.deepcopy(self.initial_observation)
        self._last_rewards: Dict[str, Dict[str, float]] = {}
        self.action_spaces = {
            agent: {
                "type": "Box",
                "low": [-1.0, -1.0, -1.0],
                "high": [1.0, 1.0, 1.0],
                "shape": [3],
                "semantic": "normalized desired velocity",
            }
            for agent in self.possible_agents
        }
        self.observation_spaces = {
            agent: {
                "type": "Dict",
                "fields": ["own_state", "neighbors", "local_links", "energy", "service", "failures", "revision"],
            }
            for agent in self.possible_agents
        }

    def _agent_observation(self, agent: str) -> Dict[str, Any]:
        uavs = {str(item.get("id")): item for item in self._observation.get("uavs", []) if isinstance(item, Mapping)}
        own = copy.deepcopy(uavs.get(agent, {}))
        own_position = own.get("measured_position", own.get("position", [0, 0, 0]))
        neighbors = []
        for other_id, other in uavs.items():
            if other_id == agent:
                continue
            other_position = other.get("measured_position", other.get("position", [0, 0, 0]))
            neighbors.append(
                {
                    "id": other_id,
                    "relative_position": [float(other_position[index]) - float(own_position[index]) for index in range(3)],
                    "active": bool(other.get("active", True)),
                    "failed": bool(other.get("failed", False)),
                }
            )
        links = [item for item in self._observation.get("links", []) if item.get("src") == agent or item.get("dst") == agent]
        return {
            "own_state": own,
            "neighbors": neighbors,
            "local_links": links,
            "energy": {"battery_soc_pct": own.get("battery_soc_pct", 100.0)},
            "service": copy.deepcopy(self._observation.get("service_requirements", {})),
            "failures": copy.deepcopy(self._observation.get("failures", [])),
            "revision": self._observation.get("revision_id", ""),
            "action_mask": {"move": bool(own.get("active", True) and not own.get("failed", False))},
        }

    def reset(self, seed: Optional[int] = None, options: Optional[Mapping[str, Any]] = None):
        self._rng = random.Random(0 if seed is None else int(seed))
        self._step_count = 0
        self._observation = copy.deepcopy(self.initial_observation)
        if options and isinstance(options.get("observation"), Mapping):
            self._observation = copy.deepcopy(dict(options["observation"]))
        self.agents = [
            agent
            for agent in self.possible_agents
            if self._agent_observation(agent)["own_state"].get("active", True)
        ]
        observations = {agent: self._agent_observation(agent) for agent in self.agents}
        infos = {agent: {"seed": seed, "reward_terms": {}} for agent in self.agents}
        return observations, infos

    def _reward(self, agent: str, command: list[float], accepted: bool, shield: Mapping[str, Any]) -> tuple[float, Dict[str, float]]:
        own = self._agent_observation(agent)["own_state"]
        formation_error = float(own.get("formation_error_m", 0.0))
        control_effort = math.sqrt(sum(float(value) ** 2 for value in command))
        battery = float(own.get("battery_soc_pct", 100.0))
        link_preview = shield.get("link_preview", [])
        feasible_links = sum(bool(item.get("feasible")) for item in link_preview)
        connectivity = feasible_links / max(1, len(link_preview))
        continuity = float(self._observation.get("packets", {}).get("service_continuity", connectivity))
        packet_delivery = float(self._observation.get("packets", {}).get("packet_delivery_ratio", continuity))
        aoi = float(self._observation.get("packets", {}).get("mean_aoi_s", 0.0))
        safety_penalty = 0.0 if accepted else 1.0
        energy_penalty = max(0.0, (100.0 - battery) / 100.0)
        terms = {
            "formation": -self.weights.formation * formation_error,
            "connectivity": self.weights.connectivity * connectivity,
            "service_continuity": self.weights.service_continuity * continuity,
            "packet_delivery": self.weights.packet_delivery * packet_delivery,
            "safety": -self.weights.safety * safety_penalty,
            "energy": -self.weights.energy * energy_penalty,
            "control_effort": -self.weights.control_effort * control_effort,
            "age_of_information": -self.weights.age_of_information * aoi,
        }
        return sum(terms.values()), terms

    def step(self, actions: Mapping[str, Any]):
        self._step_count += 1
        uavs = {str(item.get("id")): item for item in self._observation.get("uavs", []) if isinstance(item, Mapping)}
        desired_positions: Dict[str, list[float]] = {}
        dt = float(self._observation.get("step_s", 0.1))
        max_speed = float(self.config.get("swarm", {}).get("max_horizontal_speed_mps", 12.0))
        commands: Dict[str, list[float]] = {}
        for agent in self.agents:
            raw = actions.get(agent, [0.0, 0.0, 0.0])
            if isinstance(raw, Mapping):
                raw = raw.get("velocity", raw.get("action", [0, 0, 0]))
            vector = [max(-1.0, min(1.0, float(raw[index]))) for index in range(3)]
            commands[agent] = vector
            position = uavs[agent].get("measured_position", uavs[agent].get("position", [0, 0, 0]))
            desired_positions[agent] = [float(position[index]) + vector[index] * max_speed * dt for index in range(3)]
        manifest = AlgorithmManifest(
            algorithm_id="pettingzoo_policy",
            name="PettingZoo Policy",
            version="1.0.0",
            api_version="2.0",
            category="marl_policy",
            entrypoint="policy",
            execution_mode="pettingzoo_parallel",
        )
        action = AlgorithmAction.from_mapping(
            {"desired_positions": desired_positions, "coordinate_frame": "ENU", "timestamp_s": self._observation.get("wall_time_s", 0.0)},
            manifest=manifest,
            source_revision_id=str(self._observation.get("revision_id", "offline")),
            duration_s=0.0,
        )
        # Use an explicit current time compatible with synthetic/replayed snapshots.
        action.timestamp_s = float(self._observation.get("wall_time_s", action.timestamp_s))
        shield = apply_safety_shield(action, self._observation, self.config, project=True, require_connectivity=True)
        accepted_positions = shield.action.get("payload", {}).get("desired_positions", {})
        for item in self._observation.get("uavs", []):
            uav_id = str(item.get("id"))
            if uav_id in accepted_positions:
                item["commanded_position"] = accepted_positions[uav_id]
                item["simulated_position"] = accepted_positions[uav_id]
                item["measured_position"] = accepted_positions[uav_id]
        rewards: Dict[str, float] = {}
        infos: Dict[str, Dict[str, Any]] = {}
        for agent in self.agents:
            reward, terms = self._reward(agent, commands[agent], shield.accepted, shield.to_dict())
            rewards[agent] = reward
            infos[agent] = {"reward_terms": terms, "shield": shield.to_dict()}
        self._last_rewards = {agent: infos[agent]["reward_terms"] for agent in self.agents}
        terminated = self._step_count >= self.max_steps
        terminations = {agent: False for agent in self.agents}
        truncations = {agent: terminated for agent in self.agents}
        observations = {agent: self._agent_observation(agent) for agent in self.agents}
        if terminated:
            self.agents = []
        return observations, rewards, terminations, truncations, infos

    def state(self) -> Dict[str, Any]:
        return copy.deepcopy(self._observation)

    @property
    def reward_decomposition(self) -> Dict[str, Dict[str, float]]:
        return copy.deepcopy(self._last_rewards)
