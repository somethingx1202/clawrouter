"""Tests for the LatencyAndQualityAwareProbing CustomRouter."""

import pytest
from pathlib import Path

from solutions.custom_router import CustomRouter
from src.model_registry import MODEL_REGISTRY, ModelTier
from src.router import BaseRouter


# Minimal test profiles for deterministic testing
TEST_PROFILES = {
    "metadata": {
        "probed_at": "test", "probe_queries_per_category": 2,
        "source": "test", "evaluator_model": "test", "models_probed": [],
        "total_probes": 0,
    },
    "quality_thresholds": {
        "simple": 4.0, "moderate": 5.0, "complex": 6.0,
        "reasoning": 5.5, "coding": 5.5,
    },
    "agents": {
        "gemma-3-4b": {
            "tier": "small",
            "simple":    {"cloud": {"latency_median_ms": 2000, "quality_avg": 6.0},
                          "edge":  {"latency_median_ms": 400,  "quality_avg": 6.0}},
            "moderate":  {"cloud": {"latency_median_ms": 10000, "quality_avg": 4.5},
                          "edge":  {"latency_median_ms": 2000,  "quality_avg": 4.5}},
            "complex":   {"cloud": {"latency_median_ms": 15000, "quality_avg": 3.0},
                          "edge":  {"latency_median_ms": 3000,  "quality_avg": 3.0}},
            "reasoning": {"cloud": {"latency_median_ms": 5000,  "quality_avg": 4.0},
                          "edge":  {"latency_median_ms": 1000,  "quality_avg": 4.0}},
            "coding":    {"cloud": {"latency_median_ms": 12000, "quality_avg": 5.0},
                          "edge":  {"latency_median_ms": 2400,  "quality_avg": 5.0}},
        },
        "mistral-small-24b": {
            "tier": "medium",
            "simple":    {"cloud": {"latency_median_ms": 3000, "quality_avg": 7.5}},
            "moderate":  {"cloud": {"latency_median_ms": 8000, "quality_avg": 7.0}},
            "complex":   {"cloud": {"latency_median_ms": 12000, "quality_avg": 7.5}},
            "reasoning": {"cloud": {"latency_median_ms": 6000, "quality_avg": 6.5}},
            "coding":    {"cloud": {"latency_median_ms": 10000, "quality_avg": 7.0}},
        },
        "llama-3.3-70b": {
            "tier": "large",
            "simple":    {"cloud": {"latency_median_ms": 4000, "quality_avg": 8.0}},
            "moderate":  {"cloud": {"latency_median_ms": 15000, "quality_avg": 8.5}},
            "complex":   {"cloud": {"latency_median_ms": 20000, "quality_avg": 9.0}},
            "reasoning": {"cloud": {"latency_median_ms": 10000, "quality_avg": 8.0}},
            "coding":    {"cloud": {"latency_median_ms": 18000, "quality_avg": 8.5}},
        },
    },
}


class TestCustomRouterBasics:
    """Test basic router behavior."""

    def test_is_base_router(self):
        router = CustomRouter(profiles=TEST_PROFILES)
        assert isinstance(router, BaseRouter)

    def test_name(self):
        router = CustomRouter(profiles=TEST_PROFILES)
        assert router.name == "LatencyAndQualityAwareProbing"

    def test_returns_tuple(self):
        router = CustomRouter(profiles=TEST_PROFILES)
        result = router.route("What is 2+2?")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_valid_model(self):
        router = CustomRouter(profiles=TEST_PROFILES)
        model_key, deployment = router.route("What is 2+2?")
        assert model_key in MODEL_REGISTRY

    def test_returns_valid_deployment(self):
        router = CustomRouter(profiles=TEST_PROFILES)
        _, deployment = router.route("What is 2+2?")
        assert deployment in ("edge", "cloud")

    def test_edge_only_for_small(self):
        router = CustomRouter(profiles=TEST_PROFILES)
        model_key, deployment = router.route("What is 2+2?")
        if deployment == "edge":
            assert MODEL_REGISTRY[model_key].tier == ModelTier.SMALL

    def test_call_count_increments(self):
        router = CustomRouter(profiles=TEST_PROFILES)
        router.route("query 1")
        router.route("query 2")
        assert router.call_count == 2

    def test_deterministic(self):
        router = CustomRouter(profiles=TEST_PROFILES)
        r1 = router.route("What is the capital of France?")
        r2 = router.route("What is the capital of France?")
        assert r1 == r2


class TestRoutingDecisions:
    """Test that routing makes intelligent decisions based on profiles."""

    def test_simple_query_prefers_edge(self):
        """Simple queries should prefer edge (lowest latency)."""
        router = CustomRouter(profiles=TEST_PROFILES)
        model_key, deployment = router.route("What is 2+2?")
        # gemma-3-4b@edge has 400ms vs mistral@cloud 3000ms
        # gemma-3-4b quality 6.0 >= threshold 4.0, so edge should win
        assert deployment == "edge"

    def test_complex_query_picks_quality_model(self):
        """Complex queries need models that meet quality threshold 6.0."""
        router = CustomRouter(profiles=TEST_PROFILES)
        model_key, deployment = router.route(
            "Design a distributed system architecture for handling millions of users."
        )
        # gemma-3-4b complex quality 3.0 < threshold 6.0 -> excluded
        # mistral complex quality 7.5 >= 6.0, latency 12000ms
        # llama complex quality 9.0 >= 6.0, latency 20000ms
        # mistral wins (lower latency)
        assert model_key == "mistral-small-24b"
        assert deployment == "cloud"

    def test_coding_query_routes_correctly(self):
        """Coding queries should route to a model meeting coding threshold."""
        router = CustomRouter(profiles=TEST_PROFILES)
        model_key, deployment = router.route(
            "Implement a rate limiter using the token bucket algorithm in Python."
        )
        # Coding threshold 5.5
        # gemma-3-4b coding quality 5.0 < 5.5 -> excluded
        # mistral coding quality 7.0 >= 5.5, latency 10000ms
        # llama coding quality 8.5 >= 5.5, latency 18000ms
        # mistral wins (lower latency)
        assert model_key == "mistral-small-24b"

    def test_threshold_override(self):
        """Custom thresholds should override profile thresholds."""
        overrides = {
            "simple": 7.0, "moderate": 7.0, "complex": 7.0,
            "reasoning": 7.0, "coding": 7.0,
        }
        router = CustomRouter(profiles=TEST_PROFILES, threshold_override=overrides)
        model_key, _ = router.route("What is 2+2?")
        # With threshold 7.0 for simple:
        # gemma-3-4b 6.0 < 7.0 -> excluded
        # mistral 7.5 >= 7.0, llama 8.0 >= 7.0
        # mistral wins (lower latency 3000 vs 4000)
        assert model_key == "mistral-small-24b"

    def test_fallback_when_no_model_meets_threshold(self):
        """When no model meets threshold, pick highest quality."""
        overrides = {
            "simple": 99.0, "moderate": 99.0, "complex": 99.0,
            "reasoning": 99.0, "coding": 99.0,
        }
        router = CustomRouter(profiles=TEST_PROFILES, threshold_override=overrides)
        model_key, _ = router.route("What is 2+2?")
        # No model meets 99.0 -> fallback to highest quality for simple
        # llama 8.0 > mistral 7.5 > gemma 6.0
        assert model_key == "llama-3.3-70b"


class TestLoadFromFile:
    """Test loading profiles from JSON file."""

    def test_loads_from_default_path(self):
        """Should load from solutions/agent_profiles.json if it exists."""
        profile_path = Path("solutions/agent_profiles.json")
        if profile_path.exists():
            router = CustomRouter()
            assert router.name == "LatencyAndQualityAwareProbing"
            model_key, deployment = router.route("Hello world")
            assert model_key in MODEL_REGISTRY
