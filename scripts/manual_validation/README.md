# Manual Validation Scripts

These scripts are **not part of the default `pytest` test surface**.
They require external dependencies (OpenAI API key, AG2, reportlab, running Streamlit)
and are intended for manual or credentialed validation only.

## Files

| Script | Purpose | Requirements |
|--------|---------|-------------|
| `test_pipeline.py` | Heavy E2E pipeline test | AG2 + OpenAI API key + reportlab |
| `test_startup.py` | Subprocess-based Streamlit startup check | Running Streamlit instance |

## How to run

```bash
# E2E pipeline test (requires OPENAI_API_KEY)
python -m pytest scripts/manual_validation/test_pipeline.py -v

# Startup test (requires Streamlit running)
python scripts/manual_validation/test_startup.py
```

## Why not in `tests/`?

These checks require live credentials or running services and are not suitable
for the default CI/local `pytest tests/` surface. If a proper E2E CI stage is
added later, they can be moved to `tests/e2e/` with a `@pytest.mark.e2e` marker.
