# Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

## Prerequisites

Install uv (if not already installed):

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Importing (Recreating) the Environment

### Option 1: Using `uv sync` (recommended)

If the project contains `pyproject.toml` and `uv.lock`, this is the simplest and most reproducible method. It creates the virtual environment and installs exact locked versions in one step:

```bash
uv sync
```

### Option 2: Using `requirements.txt`

If you only have the `requirements.txt` (e.g. sharing with someone who doesn't use uv projects), create the environment manually:

```bash
# Create a new virtual environment
uv venv

# Activate it
source .venv/bin/activate    # Linux / macOS
.venv\Scripts\activate       # Windows

# Install dependencies
uv pip install -r requirements.txt
```

## Running the Project

After setting up the environment, copy `.env.example` to `.env` and add your OpenRouter API key:

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY=your_key_here
```

Run the evaluation:

```bash
uv run python solutions/run_eval.py
```

Run the multi-round evaluation:

```bash
uv run python solutions/run_eval_x10.py
```

Run tests:

```bash
uv run pytest tests/ -v
```
