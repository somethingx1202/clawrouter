"""
Evaluate the CustomRouter against baselines.

Benchmarks each router individually with cooldown delays between them
to avoid exhausting OpenRouter free-tier rate limits. Uses max_concurrent=2
and 60s cooldowns between routers.

Usage: uv run python solutions/run_eval.py
"""

import asyncio

from src.benchmarking import (
    benchmark_router,
    print_benchmark_summary,
    print_router_comparison,
    ALL_QUERIES,
)
from src.router import NaiveRouter, StaticRouter
from solutions.custom_router import CustomRouter

# Cooldown between routers to let rate limits reset
COOLDOWN_SECONDS = 60
MAX_CONCURRENT = 2


async def benchmark_with_cooldown(router, queries, evaluator_model, seed, label=None):
    """Benchmark a single router, printing its name."""
    name = label or router.name
    print(f"\n  Benchmarking: {name}")
    print(f"  {'-' * 40}")
    results = await benchmark_router(
        router=router,
        queries=queries,
        evaluator_model=evaluator_model,
        seed=seed,
        max_concurrent=MAX_CONCURRENT,
    )
    return results


async def main():
    print("=" * 80)
    print("CUSTOM ROUTER EVALUATION")
    print("=" * 80)

    all_results = {}
    queries = ALL_QUERIES
    evaluator_model = "trinity-mini"
    seed = 42

    # Define routers in order
    routers = [
        NaiveRouter(edge_probability=0.5),
        StaticRouter("gemma-3-4b"),
        StaticRouter("mistral-small-24b"),
        CustomRouter(),
    ]

    for i, router in enumerate(routers):
        if i > 0:
            print(f"\n  >> Cooldown {COOLDOWN_SECONDS}s to avoid rate limits...")
            await asyncio.sleep(COOLDOWN_SECONDS)

        results = await benchmark_with_cooldown(
            router, queries, evaluator_model, seed
        )
        all_results[router.name] = results

    # Print individual summaries
    for router_name, results in all_results.items():
        print_benchmark_summary(results, router_name)

    # Print comparison
    print_router_comparison(all_results)


if __name__ == "__main__":
    asyncio.run(main())
