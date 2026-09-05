# Python Package Readiness Report

## Summary

The Python SDK is locally installable from `sdk-python` as the `ai-governance`
distribution, exposing the import package `ai_governance`.

This milestone prepares local editable installs only. The package is not ready
for PyPI publication yet.

## Package Structure

```text
sdk-python/
  pyproject.toml
  README.md
  ai_governance/
    __init__.py
    client.py
    core/
    sinks/
    adapters/
    discovery/
    privacy/
```

The public import package is:

```python
import ai_governance
```

The distribution name is:

```text
ai-governance
```

## Local Install

Editable install from the repository root:

```powershell
python -m pip install -e ./sdk-python
```

In this repository's conda-based Windows environment, the equivalent command is:

```powershell
conda run python -m pip install -e ./sdk-python
```

## Optional Extras

The base package has no required third-party runtime dependencies.

Optional extras:

```powershell
python -m pip install -e "./sdk-python[openai]"
python -m pip install -e "./sdk-python[anthropic]"
python -m pip install -e "./sdk-python[fastapi]"
python -m pip install -e "./sdk-python[all]"
```

Additional compatibility extras are available for legacy or ACAP workflows:

```powershell
python -m pip install -e "./sdk-python[langchain]"
python -m pip install -e "./sdk-python[acap]"
```

## Public API

Primary SDK entry points:

```python
from ai_governance import GovernanceClient
from ai_governance.core import EventBuilder, SessionTracker, validate_event
from ai_governance.sinks import JsonlSink, HttpSink
```

Supported instrumentation surfaces:

- `GovernanceClient.tool(...)` for synchronous Python functions.
- `GovernanceClient.trace(...)` for synchronous trace/session grouping.
- `GovernanceClient.openai_client(...)` for direct OpenAI SDK wrapping.
- `GovernanceClient.anthropic_client(...)` for direct Anthropic SDK wrapping.
- `ai_governance.adapters.fastapi.GovernanceMiddleware` for FastAPI request traces.
- `GovernanceCallback` remains available for LangChain when `langchain-core` is installed.

## Not Ready For PyPI Yet

Before publishing to PyPI or TestPyPI:

- Replace placeholder license and author metadata with final legal/project metadata.
- Decide final distribution name: `ai-governance` vs. `ai-governance-sdk`.
- Add classifiers, project URLs, and long-description validation.
- Decide whether legacy PoC modules such as ACAP/report helpers should remain in the SDK package or move to separate tooling.
- Add packaging CI for build, wheel install, editable install, and import checks.
- Add versioning and release process documentation.
- Audit package data inclusion if schema/control-library files are expected inside installed wheels.
- Run tests in a clean virtual environment with only selected extras installed.
