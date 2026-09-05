# TestPyPI Release Report

## Summary

Released `agent-governance-sdk` version `0.1.0` to TestPyPI.

TestPyPI release URL:

```text
https://test.pypi.org/project/agent-governance-sdk/0.1.0/
```

Release preparation completed on 2026-08-22 in the local Windows environment.

## Package Metadata

Distribution name:

```text
agent-governance-sdk
```

Import package:

```python
import ai_governance
```

Version:

```text
0.1.0
```

The public wheel excludes the moved PoC modules under `ai_governance._poc`.

## Build

Build command:

```powershell
C:\Users\shrey\anaconda4\python.exe -m build
```

Build environment:

```text
Python 3.13.5
```

Generated artifacts:

```text
sdk-python/dist/agent_governance_sdk-0.1.0-py3-none-any.whl  34115 bytes
sdk-python/dist/agent_governance_sdk-0.1.0.tar.gz            24699 bytes
```

Artifact inspection result:

```text
wheel _poc matches: []
sdist _poc matches: []
```

## Twine Check

Twine version:

```text
twine 6.2.0
```

Validation command:

```powershell
C:\Users\shrey\anaconda4\python.exe -m twine check sdk-python\dist\*
```

Result:

```text
Checking sdk-python\dist\agent_governance_sdk-0.1.0-py3-none-any.whl: PASSED
Checking sdk-python\dist\agent_governance_sdk-0.1.0.tar.gz: PASSED
```

## TestPyPI Upload

Upload command:

```powershell
C:\Users\shrey\anaconda4\python.exe -m twine upload --repository testpypi --username __token__ sdk-python\dist\*
```

Credentials were read from keyring for `https://test.pypi.org/legacy/`; no token
was stored in the repository.

Result:

```text
Uploaded agent_governance_sdk-0.1.0-py3-none-any.whl
Uploaded agent_governance_sdk-0.1.0.tar.gz
```

## Clean Install Verification

Created a clean virtual environment outside the repository:

```text
C:\Users\shrey\AppData\Local\Temp\agent-gov-testpypi-f5b21433f87945a297b04473d66c46aa
```

Install command:

```powershell
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps agent-governance-sdk==0.1.0
```

Result:

```text
Successfully installed agent-governance-sdk-0.1.0
```

Smoke verification exercised:

- `from ai_governance import GovernanceClient, fingerprint, sanitize`
- `GovernanceClient(system_id=..., jsonl_path=...)`
- `gov.tool(...)`
- `gov.trace(...)`
- local JSONL event output

Smoke result:

```text
SMOKE_OK 4 C:\Users\shrey\AppData\Local\Temp\agent-governance-sdk-smoke.jsonl
```

The smoke file contained the expected event sequence, including `chain_start`
and `tool_end`.

## Notes

- The first local rebuild attempt without elevated network access failed because
  build isolation could not download `setuptools>=64`.
- The rebuild succeeded with network access.
- Non-elevated Python artifact reads in this Windows sandbox raised
  `PermissionError`; running Twine and artifact inspection with the same access
  level as the build succeeded.
- TestPyPI may take a minute or two to show the release page after upload.

## Next Steps

Before publishing to production PyPI:

1. Confirm the final production distribution name and ownership.
2. Replace placeholder maintainer metadata if needed.
3. Add a CI release job for build, Twine check, upload, and clean install smoke
   testing.
4. Decide whether to keep generated `agent_governance_sdk.egg-info` in the
   working tree or remove it before commit.
