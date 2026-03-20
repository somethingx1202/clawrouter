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
# Run evaluation
uv run python solutions/run_eval.py

# Re-run probing to regenerate agent profiles.
uv run python solutions/run_probing.py
```