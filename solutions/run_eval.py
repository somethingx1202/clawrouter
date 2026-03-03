"""
Evaluate the CustomRouter against baselines.

Runs benchmark_router for the CustomRouter and the baselines,
then prints a comparison.

Usage: uv run python solutions/run_eval.py
"""

import asyncio

from src.benchmarking import (
    benchmark_router,
    benchmark_all_routers,
    print_benchmark_summary,
    print_router_comparison,
    SAMPLE_QUERIES,
    ALL_QUERIES,
)
from solutions.custom_router import CustomRouter


async def main():
    print("=" * 80)
    print("CUSTOM ROUTER EVALUATION")
    print("=" * 80)

    # Benchmark baselines
    print("\n--- Benchmarking baselines ---")
    all_results = await benchmark_all_routers(
        queries=ALL_QUERIES,
        evaluator_model="trinity-mini",
        seed=42,
        max_concurrent=3,
    )
    # Benchmark our custom router
    print("\n--- Benchmarking LatencyAndQualityAwareProbing ---")
    custom_router = CustomRouter()
    custom_results = await benchmark_router(
        router=custom_router,
        queries=ALL_QUERIES,
        evaluator_model="trinity-mini",
        seed=42,
        max_concurrent=3,
    )
    all_results[custom_router.name] = custom_results

    # Print individual summaries
    for router_name, results in all_results.items():
        print_benchmark_summary(results, router_name)

    # Print comparison
    print_router_comparison(all_results)


if __name__ == "__main__":
    asyncio.run(main())
