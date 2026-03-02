"""
Run probing to generate agent_profiles.json.

Equivalent to notebooks/probing.ipynb but as a standalone script.
Run with: uv run python solutions/run_probing.py
"""

import asyncio
import json
import time
import statistics
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from src.model_registry import MODEL_REGISTRY, ModelTier
from src.latency import EDGE_LATENCY_MULTIPLIER
from src.quality import evaluate_quality


assert OPENROUTER_API_KEY, "Set OPENROUTER_API_KEY in .env"

# Load probe queries (first 2 per category)
data_path = Path(__file__).parent.parent / "data" / "sample_queries_augmented_by_my_queries.json"
with open(data_path) as f:
    all_queries = json.load(f)

PROBE_QUERIES = {cat: queries[:2] for cat, queries in all_queries.items()}


async def probe_model(
    model_key: str,
    query: str,
    category: str,
    evaluator_model: str = "trinity-mini",
    max_retries: int = 3,
    base_delay: float = 15.0,
) -> dict | None:
    """Probe a single model with a single query."""
    model_config = MODEL_REGISTRY[model_key]

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                start_time = time.time()
                resp = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_config.model_id,
                        "messages": [{"role": "user", "content": query}],
                        "max_tokens": 1000,
                    },
                    timeout=120.0,
                )
                cloud_latency_ms = (time.time() - start_time) * 1000

            if resp.status_code == 429:
                delay = base_delay * (2 ** attempt)
                print(f"    Rate limited, waiting {delay:.0f}s (attempt {attempt+1})")
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            result = resp.json()

            if "choices" not in result or not result["choices"]:
                print(f"    No choices in response for {model_key}")
                await asyncio.sleep(base_delay)
                continue

            response_text = result["choices"][0]["message"]["content"]

            quality_eval = await evaluate_quality(
                query=query,
                response=response_text,
                model_key=model_key,
                evaluator_model=evaluator_model,
            )

            return {
                "cloud_latency_ms": cloud_latency_ms,
                "quality_score": quality_eval.overall_score,
                "response_preview": response_text[:200],
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                delay = base_delay * (2 ** attempt)
                print(f"    Rate limited, waiting {delay:.0f}s")
                await asyncio.sleep(delay)
            else:
                print(f"    HTTP error for {model_key}: {e}")
                return None
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                delay = base_delay * (2 ** attempt)
                print(f"    Rate limited, waiting {delay:.0f}s")
                await asyncio.sleep(delay)
            else:
                print(f"    Error probing {model_key}: {e}")
                return None

    print(f"    Failed after {max_retries} retries for {model_key}")
    return None


async def run_all_probes():
    """Probe all models across all categories."""
    raw_results = {}
    model_keys = list(MODEL_REGISTRY.keys())
    total = len(model_keys) * sum(len(qs) for qs in PROBE_QUERIES.values())
    completed = 0

    for model_key in model_keys:
        raw_results[model_key] = {}
        print(f"\nProbing {model_key} ({MODEL_REGISTRY[model_key].display_name})...")

        for category, queries in PROBE_QUERIES.items():
            raw_results[model_key][category] = []

            for i, query in enumerate(queries):
                completed += 1
                print(f"  [{completed}/{total}] {category} query {i+1}...")
                result = await probe_model(model_key, query, category)
                if result:
                    raw_results[model_key][category].append(result)
                    print(f"    latency={result['cloud_latency_ms']:.0f}ms, "
                          f"quality={result['quality_score']:.1f}")
                else:
                    print(f"    FAILED")

                await asyncio.sleep(2)

        await asyncio.sleep(5)

    return raw_results


def build_agent_profiles(raw_results: dict) -> dict:
    """Aggregate raw probe results into agent profiles with quality thresholds."""
    agents = {}
    category_qualities = {cat: [] for cat in PROBE_QUERIES}

    for model_key, categories in raw_results.items():
        tier = MODEL_REGISTRY[model_key].tier
        is_edge = tier == ModelTier.SMALL
        agent = {"tier": tier.value}

        for category, probes in categories.items():
            if not probes:
                continue

            latencies = [p["cloud_latency_ms"] for p in probes]
            qualities = [p["quality_score"] for p in probes]

            cloud_median = statistics.median(latencies)
            quality_avg = statistics.mean(qualities)

            category_qualities[category].append(quality_avg)

            entry = {
                "cloud": {
                    "latency_median_ms": round(cloud_median, 1),
                    "quality_avg": round(quality_avg, 2),
                },
            }

            if is_edge:
                entry["edge"] = {
                    "latency_median_ms": round(cloud_median * EDGE_LATENCY_MULTIPLIER, 1),
                    "quality_avg": round(quality_avg, 2),
                }

            agent[category] = entry

        agents[model_key] = agent

    quality_thresholds = {}
    for category, scores in category_qualities.items():
        if scores:
            median_q = statistics.median(scores)
            quality_thresholds[category] = round(max(0, median_q - 0.5), 2)
        else:
            quality_thresholds[category] = 0.0

    return {
        "metadata": {
            "probed_at": datetime.now(timezone.utc).isoformat(),
            "probe_queries_per_category": 2,
            "source": "sample_queries_augmented_by_my_queries.json",
            "evaluator_model": "trinity-mini",
            "models_probed": list(agents.keys()),
            "total_probes": sum(
                len(probes)
                for cats in raw_results.values()
                for probes in cats.values()
            ),
        },
        "quality_thresholds": quality_thresholds,
        "agents": agents,
    }


async def main():
    print("=" * 60)
    print("Agent Profile Probing")
    print("=" * 60)
    print(f"\nProbe queries per category:")
    for cat, qs in PROBE_QUERIES.items():
        print(f"  {cat}: {len(qs)} queries")

    raw_results = await run_all_probes()

    profiles = build_agent_profiles(raw_results)

    print("\nQuality thresholds (data-driven):")
    for cat, thresh in profiles["quality_thresholds"].items():
        print(f"  {cat}: {thresh}")

    output_path = Path(__file__).parent / "agent_profiles.json"
    with open(output_path, "w") as f:
        json.dump(profiles, f, indent=2)

    print(f"\nSaved agent profiles to {output_path}")
    print(f"Total agents: {len(profiles['agents'])}")
    for model_key, agent in profiles['agents'].items():
        cats = [c for c in agent if c != 'tier']
        print(f"  {model_key} ({agent['tier']}): {len(cats)} categories probed")


if __name__ == "__main__":
    asyncio.run(main())
