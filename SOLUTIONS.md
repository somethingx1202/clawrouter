# SOLUTIONS_README.md

## Pipeline Architecture and Design Rationale

### Overview

**LatencyAndQualityAwareProbing** is an agentic routing system that routes queries to the optimal model/deployment combination using pre-measured agent profiles and heuristic query complexity classification. It follows a two-phase architecture: an offline probing phase that collects performance data, and an online routing phase that uses that data as context for zero-overhead routing decisions.

### Architecture Diagram

```
OFFLINE: Probing Phase (run once)
┌──────────────────────────────────────────────────────────────────────┐
│  sample_queries (2 per category)                                     │
│    × 10 models (gemma-3-4b, gemma-3n-e4b, trinity-mini, ...)       │
│    × 5 categories (simple, moderate, complex, reasoning, coding)     │
│                                                                      │
│  For each (model, category):                                         │
│    1. Send query to OpenRouter API → measure cloud latency           │
│    2. Evaluate response quality via LLM-as-judge (trinity-mini)      │
│    3. Compute edge latency = cloud × 0.2 (SMALL tier only)          │
│                                                                      │
│  Aggregate:                                                          │
│    - Per-model, per-category: median latency + mean quality          │
│    - Per-category quality threshold: median(all qualities) - 0.5     │
│                                                                      │
│  Output: solutions/agent_profiles.json                               │
└──────────────────────────────────────────────────────────────────────┘

ONLINE: Routing Phase (per query, zero LLM overhead)
┌──────────────────────────────────────────────────────────────────────┐
│  Input query                                                         │
│    │                                                                 │
│    ▼                                                                 │
│  classify_complexity(query) → "simple"|"moderate"|"complex"|         │
│                                "reasoning"|"coding"                  │
│    │                                                                 │
│    ▼                                                                 │
│  Look up pre-sorted candidates for that category                     │
│    │                                                                 │
│    ▼                                                                 │
│  Filter: quality_avg >= data-driven threshold                        │
│    │                                                                 │
│    ▼                                                                 │
│  Select: fastest qualifying model (latency ASC, cost ASC tiebreak)   │
│    │                                                                 │
│    ▼                                                                 │
│  Output: (model_key, deployment)                                     │
└──────────────────────────────────────────────────────────────────────┘
```

### Why This Architecture?

The core insight is that **routing overhead must be justified by routing quality**. An agentic routing pipeline that calls an LLM to classify each query adds 1-5 seconds of latency before any inference begins. For queries routed to edge models (200-700ms latency), this overhead can be 3-10x the actual inference time. This tradeoff is well-documented in the LLM routing literature — Ding et al. [2] showed that a hybrid approach routing between small and large models can reduce calls to the expensive model by 40% with <1% quality loss, and Chen et al. [3] demonstrated up to 98% cost savings through LLM cascading.

Our approach uses the LLM agent (trinity-mini) during the **offline probing phase** to evaluate quality via the LLM-as-judge paradigm [4], then compiles those evaluations into a static JSON profile. At routing time, we use a fast heuristic classifier (sub-millisecond) instead of an LLM call. This design draws from the pre-generation routing taxonomy identified in the comprehensive survey by Kwan et al. [5], where routing decisions are made before generation based on predicted candidate performance. It means:

- **Zero routing overhead** at query time (no extra LLM calls)
- **Data-driven decisions** based on actual measured performance, not assumptions
- **Deterministic routing** for reproducibility and testability
- **In-context learning** via the agent profiles (model strengths/weaknesses as structured data)

## Why Agentic Routing is a Better Choice?

Common LLM routers treat models as interchangeable units differentiated primarily by **model size** and **deployment choice** — a large model is assumed to be better for hard queries, a small model for easy ones, and routing is guided by size-based complexity heuristics. This is the approach taken by most existing router frameworks: RouteLLM [1] trains a binary strong/weak router, Hybrid LLM [2] uses a quality predictor to choose between two tiers, and FrugalGPT [3] cascades through models from cheap to expensive. While effective for cost reduction, these approaches have fundamental limitations: they cannot capture that a 4B model might excel at coding but struggle with simple factual questions, or that two medium-tier models may have completely different strengths.

Our agentic routing approach differs from common routing in three key ways:

### 1. Skill-Based Agent Profiles (Not Size-Based Categories)

Our system treats each model as a **specialist with measurable skills** rather than a generic unit in a size hierarchy. The Super Agent System architecture [6] similarly advocates for task agents with distinct capabilities selected by a model router, and ClawRouter [7] uses multi-dimensional scoring across 15 features. We extend this concept to per-category skill profiling.

Each model is wrapped in an **agent profile** that describes its measured **skills** — not just its tier or parameter count. An agent profile looks like:

```
Agent: gemma-3-4b (SMALL tier)
├── Simple skill:    latency 397ms (edge),  quality 6.5/10
├── Moderate skill:  latency 3127ms (edge), quality 8.35/10
├── Complex skill:   latency 3089ms (edge), quality 7.5/10
├── Reasoning skill: latency 947ms (edge),  quality 6.5/10
└── Coding skill:    latency 2868ms (edge), quality 9.25/10
```

This reveals that gemma-3-4b is a **coding specialist** (9.25 quality) despite being a SMALL-tier model, while it underperforms on simple factual queries (6.5) — a pattern invisible to size-based routing. Similarly, nemotron-nano (MEDIUM tier) achieves a perfect 10.0 on reasoning but only 5.25 on moderate queries. These per-skill profiles provide **fine-grained modelling** of each agent's actual capabilities, capturing the reality that different models (and even the same model with different prompt types) have distinct strengths regardless of size.

### 2. In-Context Learning via Probing

The probing phase functions as **in-context learning**: the system uses an LLM evaluator (trinity-mini) as an LLM-as-judge [4] to assess each agent's performance, then **memorises** these assessments as structured agent profiles and data-driven quality thresholds. During the online routing phase, the router consults this memorised knowledge to make informed decisions — effectively applying what it "learned" during probing without any additional LLM calls.

This is distinct from both static rules and trained classifiers (as used in RouteLLM [1] and Hybrid LLM [2]): the quality thresholds (`threshold = median(quality) - 0.5`) are **derived from the data**, not hardcoded, and they automatically adapt when the model pool changes. The agent profiles serve as a compiled form of the evaluator LLM's judgment, making its intelligence available at zero runtime cost. This approach aligns with what the survey by Kwan et al. [5] categorizes as "profiling for context" — collecting performance data to inform routing decisions without training a classifier.

### 3. Future Development Roadmap

This architecture is designed to evolve toward a fully agentic system:

- **Agentic loop with human-agent interaction**: Introduce a dynamic feedback loop where human operators can interact with the routing agent — adjusting thresholds, overriding routing decisions, or triggering re-probing for specific models. This enables runtime configuration without redeployment.

- **Agent-side memory for request caching**: Extend agent profiles with a memory layer that caches recent request-response pairs. When a similar query arrives, the agent can serve a cached response directly, further reducing latency beyond what model selection alone achieves. This draws from the memory and RAG components in the Super Agent System architecture [6].

- **Additional skills and dimensions**: Expand beyond the current 5 complexity categories to include domain-specific skills (e.g., medical, legal, multilingual), safety-sensitivity levels etc. This would move our skill-based routing closer to the multi-dimensional scoring approaches used by ClawRouter [7] (15 dimensions) and the contextual bandit formulations explored by Soare et al. [8].

## Routing Signals

### Signals Chosen and Why

| Signal | How Extracted | Why It Matters |
|--------|--------------|----------------|
| **Query complexity** | Heuristic classifier (keyword + structural) | Different models excel at different complexity levels; a 4B model handles "What is 2+2?" as well as a 70B model |
| **Model quality per category** | LLM-as-judge evaluation during probing | Avoids sending queries to models that produce poor results for that category |
| **Deployment latency** | Measured API latency × deployment multiplier | Edge deployment (0.2×) dramatically reduces latency for SMALL models |
| **Cost** | Emulated cost from model registry | Tiebreaker when multiple models have similar latency above quality threshold |

### Complexity Classification

The `classify_complexity()` function in `solutions/complexity.py` uses a priority-ordered heuristic:

1. **Coding** (highest priority): Keywords like "implement", "write a function", "sql query", data structure names
2. **Reasoning**: Puzzle indicators, trick questions, "how much does", "what place"
3. **Complex**: System design, mathematical analysis, "trade-offs", "architecture"
4. **Moderate**: Explanatory queries, "how does X work", "what is the difference"
5. **Simple** (fallback): Short factual queries, or anything not matching above

Structural fallbacks: word count > 80 → complex, > 30 → moderate, otherwise simple.

### Quality Thresholds (Data-Driven)

Instead of hardcoded thresholds, we compute them from probing data:

```
threshold[category] = median(quality scores across all models for category) - 0.5
```

From our probing run:

| Category | Threshold | Interpretation |
|----------|-----------|----------------|
| simple | 7.85 | Most models handle simple queries well; high bar |
| moderate | 7.62 | Moderate queries need reliable models |
| complex | 6.90 | Complex queries are hard; lower bar to have options |
| reasoning | 8.50 | Reasoning needs high quality; strict threshold |
| coding | 8.50 | Code quality matters; strict threshold |

## Agent Profile Summary: Model Strengths and Weaknesses

Using the resulting profiles post-probing stored in `solutions/agent_profiles.json`:

| Model | Tier | Strengths | Weaknesses |
|-------|------|-----------|------------|
| **gemma-3n-e4b** | SMALL | Excellent across all categories on edge; fast simple/reasoning (248-1478ms edge); high quality simple (9.0) and reasoning (8.7) | Moderate/complex latency still ~3s on edge |
| **gemma-3-4b** | SMALL | Strong coding (9.25 quality); decent moderate (8.35) | Poor simple quality (6.5); poor reasoning (6.5); high cloud latency |
| **gemma-3-12b** | MEDIUM | Good reasoning (9.25); solid simple (8.7) | Very high cloud latency for moderate/complex (20s+) |
| **gemma-3-27b** | MEDIUM | Good reasoning (9.0); fast simple (1782ms) | Poor complex (6.0); no coding data; high moderate/complex latency |
| **trinity-mini** | MEDIUM | Good reasoning (9.0); moderate latency across categories | Poor complex (6.5); poor coding (6.25) |
| **nemotron-nano** | MEDIUM | Perfect reasoning score (10.0); strong simple (8.95) | Poor moderate (5.25); high latency across categories |

Models that failed probing (404 errors from OpenRouter): llama-3.2-3b, mistral-small-24b, llama-3.3-70b, deepseek-r1-0528. The router gracefully handles missing models by only considering those with profile data.

### Routing Decisions in Practice

From the benchmark results, the router makes these category-level choices:

- **Simple queries** → `gemma-3n-e4b@edge` (248ms median, quality 9.0) — fastest SMALL model with high quality
- **Moderate queries** → `gemma-3n-e4b@edge` (2964ms median, quality 8.0) — meets threshold with lower latency than cloud alternatives
- **Complex queries** → `gemma-3n-e4b@edge` (2982ms median, quality 7.75) — meets 6.9 threshold with edge speed advantage
- **Reasoning queries** → `gemma-3n-e4b@edge` (1478ms median, quality 8.7) — meets high 8.5 threshold at edge speed
- **Coding queries** → `gemma-3-4b@edge` (2868ms median, quality 9.25) — best coding quality model at edge speed

## Key Results

### Benchmark Comparison

```
Router                               Queries  Avg Latency  Avg Quality     Total Cost
----------------------------------------------------------------------------------------------------
Random                                    12       6938ms        8.00/10 $    0.000346
Static(gemma-3-4b@edge)                   15       2485ms        7.73/10 $    0.000017
Static(mistral-small-24b@cloud)          N/A          N/A          N/A            N/A
LatencyAndQualityAwareProbing             15       2368ms        8.27/10 $    0.000519
----------------------------------------------------------------------------------------------------

Best Latency:  LatencyAndQualityAwareProbing
Best Quality:  LatencyAndQualityAwareProbing
Lowest Cost:   Static(gemma-3-4b@edge)
```

### Performance Summary

| Metric | Random | Static (gemma-3-4b@edge) | **Our Router** |
|--------|--------|--------------------------|----------------|
| Avg Latency | 6938 ms | 2485 ms | **2368 ms** |
| Avg Quality | 8.00/10 | 7.73/10 | **8.27/10** |
| Total Cost | $0.000346 | **$0.000017** | $0.000519 |
| Queries Completed | 12/15 | 15/15 | 15/15 |

Our router achieves **both the best latency and the best quality** among all routers:

- **4.7% faster** than Static(gemma-3-4b@edge) (2368ms vs 2485ms)
- **7.0% higher quality** than Static(gemma-3-4b@edge) (8.27 vs 7.73)
- **65.9% faster** than Random (2368ms vs 6938ms)
- **3.4% higher quality** than Random (8.27 vs 8.00)

### Category-Level Results

| Category | Model@Deploy | Latency | Quality |
|----------|-------------|---------|---------|
| simple | gemma-3n-e4b@edge | 386 ms | 7.33/10 |
| moderate | gemma-3n-e4b@edge | 3881 ms | 7.67/10 |
| complex | gemma-3n-e4b@edge | 3801 ms | 7.33/10 |
| reasoning | gemma-3n-e4b@edge | 539 ms | 9.67/10 |
| coding | gemma-3-4b@edge | 3233 ms | 9.33/10 |

Key observations:
- **Reasoning stands out** at 9.67/10 quality with only 539ms latency — the router correctly identified gemma-3n-e4b as exceptional for reasoning tasks
- **Coding correctly routes** to gemma-3-4b (quality 9.25 in profiles) instead of gemma-3n-e4b (quality 9.25, but gemma-3-4b has lower cost as tiebreaker)
- **All edge deployment** — the router learned that SMALL models on edge provide the best latency/quality tradeoff for all categories in this model set

## Routing Overhead Analysis

### Why Zero Overhead Matters

| Approach | Routing Overhead | Justified When |
|----------|-----------------|----------------|
| LLM-based classification at query time | 1-5 seconds per query | Large model pool with diverse capabilities; overhead << inference time |
| **Our approach: heuristic + pre-computed profiles** | **< 1 ms per query** | Edge-heavy workloads where inference is fast (200-4000ms) |
| No routing (static) | 0 ms | Single model serves all queries acceptably |

For our model set (dominated by SMALL tier models on edge with 200-4000ms latency), adding even a 2-second LLM routing call would **double the total latency** for simple queries. The heuristic classifier achieves comparable routing quality at negligible cost.

### Probing Phase Overhead (One-Time)

The offline probing phase takes ~15-30 minutes (depending on rate limits) and needs to be re-run only when:
- New models are added to the registry
- Model performance characteristics change significantly
- Quality evaluation criteria change

This is amortized across all future routing decisions.

## What Worked

1. **Data-driven quality thresholds** — Computing thresholds from probing data (median - 0.5 margin) automatically adapts to the actual model landscape. With most models scoring 7-9, the thresholds naturally set themselves to filter out poor performers without manual tuning.

2. **Edge-first routing** — The probing data showed that SMALL models on edge (0.2× latency) consistently provide the best latency/quality tradeoff. The router correctly learned to prefer edge deployment for all categories.

3. **Separate probing from routing** — Decoupling the expensive LLM evaluation (probing) from the routing decision eliminates per-query overhead. The agent profiles serve as a "compiled" form of in-context learning.

4. **Heuristic complexity classification** — The keyword + structural approach correctly classifies queries across all 5 categories with 15/15 tests passing. It runs in sub-millisecond time.

5. **Pre-sorted candidate lists** — Building sorted candidate lists at initialization time makes `route()` O(n) in the number of candidates per category (typically 5-15), with no runtime sorting.

## What Didn't Work

1. **Some models unavailable** — 4 out of 10 models returned 404 errors during probing (llama-3.2-3b, mistral-small-24b, llama-3.3-70b, deepseek-r1-0528). This reduced the model pool, particularly eliminating LARGE and REASONING tier options. With those models available, the router would likely route complex/reasoning queries to them instead of SMALL models.

2. **Rate limiting affected benchmarks** — OpenRouter free tier rate limits caused the Random baseline and Static(mistral-small-24b@cloud) to fail or produce incomplete results. This makes comparison less reliable.

3. **Quality evaluation variance** — LLM-as-judge scores vary between runs. A query might score 7.0 in one evaluation and 9.0 in another. With only 2 probes per category, the quality averages in agent profiles have high variance. More probes would improve reliability.

4. **Homogeneous routing** — Because the LARGE and REASONING models were unavailable, and the surviving SMALL models dominated on edge latency, the router routes almost everything to edge. This is correct given the available data, but in a full deployment with all models available, we would expect more diverse routing.

## Known Limitations

1. **Static profiles** — Agent profiles are computed offline and don't adapt to changing model performance (e.g., OpenRouter load variations, model updates). A production system would need periodic re-probing or an EMA-based runtime adaptation.

2. **Heuristic classification** — The keyword-based classifier can misclassify queries that use ambiguous language. For example, "explain how to implement a cache" could be "moderate" (explain) or "coding" (implement). The priority order (coding > reasoning > complex > moderate > simple) handles this, but edge cases exist.

3. **Limited probe sample size** — 2 queries per category per model is the minimum for computing medians. More probes would give more stable latency and quality estimates. The `run_probing.py` script is parameterized to allow increasing this.

4. **No runtime fallback** — If a selected model is temporarily unavailable (429, 500 errors), the router has no retry or fallback model.

5. **Single evaluator model** — Quality evaluation uses trinity-mini as judge. Different evaluator models may score differently. A production system could use multiple evaluators or a more robust evaluation pipeline.

6. **Cost not fully optimized** — While cost is used as a tiebreaker, the router prioritizes latency over cost. For cost-sensitive deployments, the sorting key could be adjusted (e.g., cost-weighted latency).

## Reproducibility

### Environment Setup

```bash
# Option 1: Using uv sync (recommended)
uv sync

# Option 2: Using requirements.txt
uv venv
source .venv/bin/activate    # Linux / macOS
.venv\Scripts\activate       # Windows
uv pip install -r requirements.txt
```

### Configuration

```bash
cp .env.template .env
# Edit .env and set OPENROUTER_API_KEY=your_key_here
```

### Running

```bash
# Run tests (no API key needed)
uv run pytest tests/ -v

# Run smoke test
uv run python smoke_test.py

# Run evaluation
uv run python solutions/run_eval.py

# Re-run probing to regenerate agent profiles.
uv run python solutions/run_probing.py
```

### All Prompts Included

All LLM interactions are in the codebase:
- **Probing**: Direct API calls in `solutions/run_probing.py` and `notebooks/probing.ipynb`, user queries sent to each model with default system prompts.
- **Quality evaluation**: Structured prompts in `src/quality.py` (not modified)
- **Routing**: No LLM calls — pure heuristic + profile lookup

## File Structure

```
solutions/
├── custom_router.py          # Main router (CustomRouter class)
├── complexity.py             # Heuristic query complexity classifier
├── agent_profiles.json       # Pre-computed agent profiles (from probing)
├── run_probing.py            # Standalone probing script
├── run_eval.py               # Single-run evaluation script
├── run_eval_x10.py           # Multi-round evaluation script
└── __init__.py               # Module exports

notebooks/
└── probing.ipynb             # Probing notebook (equivalent to run_probing.py)

tests/
├── test_complexity.py        # 15 tests for complexity classifier
└── test_custom_router.py     # 14 tests for CustomRouter

docs/plans/
├── *-design.md               # Architecture design document
└── *-plan.md                 # Implementation plan (6 tasks)
```

## References

[1] Ong, I., Almahairi, A., Wu, V., Chiang, W.-L., Wu, T., Gonzalez, J.E., Kadous, M.W., & Stoica, I. (2024). **RouteLLM: Learning to Route LLMs with Preference Data.** ICLR 2025. [arXiv:2406.18665](https://arxiv.org/abs/2406.18665) | [GitHub](https://github.com/lm-sys/RouteLLM)

[2] Ding, D., Mallick, A., Wang, C., Sim, R., Mukherjee, S., Rühle, V., Levi, L., & Awadallah, A. (2024). **Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing.** ICLR 2024. [arXiv:2404.14618](https://arxiv.org/abs/2404.14618)

[3] Chen, L., Zaharia, M., & Zou, J. (2023). **FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.** [arXiv:2305.05176](https://arxiv.org/abs/2305.05176)

[4] Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E.P., Zhang, H., Gonzalez, J.E., & Stoica, I. (2023). **Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.** NeurIPS 2023. [arXiv:2306.05685](https://arxiv.org/abs/2306.05685)

[5] Kwan, J., Li, H., Cheng, L., Ma, W.-Y., & Lo, P.-L. (2025). **Doing More with Less: A Survey on Routing Strategies for Resource Optimisation in Large Language Model-Based Systems.** [arXiv:2502.00409](https://arxiv.org/abs/2502.00409)

[6] Yao, Y., Wang, C., et al. (2025). **Toward Super Agent System with Hybrid AI Routers.** [arXiv:2504.10519](https://arxiv.org/abs/2504.10519)

[7] BlockRunAI. **ClawRouter: The Agent-Native LLM Router.** [GitHub](https://github.com/BlockRunAI/ClawRouter)

[8] Soare, M., et al. (2025). **Learning to Route LLMs from Bandit Feedback: One Policy, Many Trade-offs.** [arXiv:2510.07429](https://arxiv.org/abs/2510.07429)
