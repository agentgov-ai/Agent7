# Public API Surface

This document lists the supported public imports for the production PyPI
hardening path of `agent-governance-sdk`.

## Distribution

Install distribution:

```text
agent-governance-sdk
```

Runtime import package:

```python
import ai_governance
```

## Supported Public Imports

Core client:

```python
from ai_governance import GovernanceClient
```

Sinks:

```python
from ai_governance.sinks import JsonlSink
from ai_governance.sinks import HttpSink
```

Adapter modules:

```python
import ai_governance.adapters.openai
import ai_governance.adapters.anthropic
import ai_governance.adapters.fastapi
```

`ai_governance.adapters.fastapi` requires the optional `fastapi` or `starlette`
dependency to be installed.

## Compatibility And Private Modules

The `governance_probe` package is a repository-level PoC compatibility shim. It
is not included in the published `agent-governance-sdk` wheel and should not be
documented as a public SDK import path for production PyPI.

The `ai_governance._poc` package contains PoC-only tooling. It is intentionally
excluded from the wheel and sdist by package configuration and is not a public
SDK API.

Production SDK code under the published `ai_governance` package must not depend
on `ai_governance._poc`.
