"""
CustomRouter: LatencyAndQualityAwareProbing.

Routes queries to the optimal model/deployment combination based on
pre-measured agent profiles (latency + quality per complexity category).

Algorithm:
1. Classify query complexity using heuristic classifier
2. Filter models whose quality >= data-driven threshold for that category
3. Sort by latency ASC, cost ASC (tiebreaker)
4. Return the fastest qualifying model
5. Fallback: if nothing meets threshold, pick highest quality
"""

import json
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

from src.router import BaseRouter
from src.model_registry import (
    MODEL_REGISTRY,
    ModelTier,
    EDGE_COMPATIBLE_MODELS,
)

from .complexity import classify_complexity


_DEFAULT_PROFILES_PATH = Path(__file__).parent / "agent_profiles.json"


class CustomRouter(BaseRouter):
    """
    Latency-and-quality-aware router using pre-computed agent profiles.

    Loads agent profiles (latency + quality measurements per model per
    complexity category) from a JSON file or dict. Uses heuristic query
    complexity classification to select the fastest model that meets
    a data-driven quality threshold, with cost as tiebreaker.
    """

    def __init__(
        self,
        profiles: Optional[Dict[str, Any]] = None,
        profiles_path: Optional[Path] = None,
        threshold_override: Optional[Dict[str, float]] = None,
    ):
        """
        Args:
            profiles: Pre-computed agent profiles dict. If None, loads from file.
            profiles_path: Path to agent_profiles.json. Defaults to
                solutions/agent_profiles.json.
            threshold_override: Optional dict of category -> quality threshold
                to override the data-driven thresholds from profiles.
        """
        super().__init__()

        if profiles is not None:
            self._profiles = profiles
        else:
            path = profiles_path or _DEFAULT_PROFILES_PATH
            if not path.exists():
                raise FileNotFoundError(
                    f"Agent profiles not found at {path}. "
                    "Run notebooks/probing.ipynb first."
                )
            with open(path) as f:
                self._profiles = json.load(f)

        self._agents = self._profiles["agents"]
        self._thresholds = dict(self._profiles["quality_thresholds"])

        if threshold_override:
            self._thresholds.update(threshold_override)

        self._candidates = self._build_candidates()

    @property
    def name(self) -> str:
        return "LatencyAndQualityAwareProbing"

    def _build_candidates(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Pre-build sorted candidate lists per category.

        For each category, builds a list of (model_key, deployment, latency,
        quality, cost) dicts sorted by latency ASC, cost ASC.
        """
        candidates: Dict[str, List[Dict[str, Any]]] = {}
        categories = ["simple", "moderate", "complex", "reasoning", "coding"]

        for category in categories:
            cat_candidates = []

            for model_key, agent in self._agents.items():
                if category not in agent:
                    continue

                cat_data = agent[category]
                model_config = MODEL_REGISTRY.get(model_key)
                if not model_config:
                    continue

                cost = (model_config.cost_per_million_input
                        + model_config.cost_per_million_output)

                if "cloud" in cat_data:
                    cloud = cat_data["cloud"]
                    cat_candidates.append({
                        "model_key": model_key,
                        "deployment": "cloud",
                        "latency_median_ms": cloud["latency_median_ms"],
                        "quality_avg": cloud["quality_avg"],
                        "cost": cost,
                    })

                if "edge" in cat_data:
                    edge = cat_data["edge"]
                    cat_candidates.append({
                        "model_key": model_key,
                        "deployment": "edge",
                        "latency_median_ms": edge["latency_median_ms"],
                        "quality_avg": edge["quality_avg"],
                        "cost": cost,
                    })

            cat_candidates.sort(
                key=lambda c: (c["latency_median_ms"], c["cost"])
            )
            candidates[category] = cat_candidates

        return candidates

    def route(
        self,
        query: str,
        available_models: Optional[List[str]] = None,
    ) -> Tuple[str, str]:
        """
        Route a query to the optimal model and deployment.

        1. Classify complexity
        2. Filter by quality threshold
        3. Pick fastest (latency ASC, cost ASC tiebreaker)
        4. Fallback to highest quality if nothing meets threshold
        """
        self.call_count += 1

        category = classify_complexity(query)
        threshold = self._thresholds.get(category, 0.0)
        candidates = self._candidates.get(category, [])

        if available_models:
            candidates = [
                c for c in candidates if c["model_key"] in available_models
            ]

        qualifying = [c for c in candidates if c["quality_avg"] >= threshold]

        if qualifying:
            best = qualifying[0]
        elif candidates:
            best = max(candidates, key=lambda c: c["quality_avg"])
        else:
            best = {
                "model_key": EDGE_COMPATIBLE_MODELS[0],
                "deployment": "edge",
            }

        model_key = best["model_key"]
        deployment = best["deployment"]

        self.routing_history.append((query[:50], model_key, deployment))
        return (model_key, deployment)
