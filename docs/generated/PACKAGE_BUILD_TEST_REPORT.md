# Package Build Test Report

## Build Tools

Installed build/check tooling in the local conda environment:

```powershell
conda run python -m pip install build twine
```

`twine 7.0.0` required `packaging>=26.1`, which conflicted with existing
packages in the local conda environment. The environment was adjusted to:

```text
twine 6.2.0
packaging 24.2
rich 14.3.4
```

The clean wheel-test virtual environment reported:

```text
No broken requirements found.
```

## Build Command

```powershell
conda run python -m build ./sdk-python
```

The first sandboxed build attempt failed because build isolation could not
download `setuptools>=64`. The same command succeeded with network access.

## Generated Dist Files

```text
sdk-python/dist/ai_governance-0.1.0-py3-none-any.whl  57294 bytes
sdk-python/dist/ai_governance-0.1.0.tar.gz            44611 bytes
```

Transient generated directories `sdk-python/build` and
`sdk-python/ai_governance.egg-info` were removed after the build. The
`sdk-python/dist` artifacts were kept.

## Twine Check

```powershell
conda run python -m twine check sdk-python\dist\ai_governance-0.1.0-py3-none-any.whl sdk-python\dist\ai_governance-0.1.0.tar.gz
```

Result:

```text
Checking sdk-python\dist\ai_governance-0.1.0-py3-none-any.whl: PASSED
Checking sdk-python\dist\ai_governance-0.1.0.tar.gz: PASSED
```

Note: the build artifacts were created by an escalated build process. In this
Windows sandbox, non-escalated Python could stat but not open those files.
Running `twine check` with the same access level succeeded.

## Clean Install

Created a clean virtual environment outside the repository:

```text
C:\Users\shrey\AppData\Local\Temp\ai_governance_wheel_test_5fad6ec99dee476288191782684c02c7
```

Installed the built wheel:

```powershell
C:\Users\shrey\AppData\Local\Temp\ai_governance_wheel_test_5fad6ec99dee476288191782684c02c7\Scripts\python.exe -m pip install C:\Users\shrey\Downloads\Restaurant_Agent\sdk-python\dist\ai_governance-0.1.0-py3-none-any.whl
```

Result:

```text
Successfully installed ai-governance-0.1.0
```

## Import And Minimal Script

Ran from outside the repository:

```python
from ai_governance import GovernanceClient
```

Minimal script result:

```text
{'result': 5, 'event_types': ['chain_start', 'tool_start', 'tool_end', 'chain_end'], 'event_count': 4}
```

The script used `GovernanceClient`, `gov.tool`, `gov.trace`, and local JSONL
output.

## Optional Extras

Tested in the same clean virtual environment:

```powershell
pip install ".\sdk-python[openai]"
pip install ".\sdk-python[anthropic]"
pip install ".\sdk-python[fastapi]"
```

Results:

```text
openai extra: installed, openai 3.1.0
anthropic extra: installed, anthropic 0.122.0
fastapi extra: installed, fastapi 0.141.1
pip check: No broken requirements found.
```

## Package Name Risk

PyPI name checks found both current/obvious names already occupied:

- `ai-governance`: https://pypi.org/project/ai-governance/
- `ai-governance-sdk`: https://pypi.org/project/ai-governance-sdk/

Do not publish this package with either name unless ownership is confirmed or
the project is intentionally renamed.

Safer naming options to consider before TestPyPI/PyPI:

- `governance-evidence-sdk`
- `agent-governance-evidence`
- `ai-evidence-governance`
- a scoped/company-specific package name

## Recommended Next Step

Before TestPyPI:

1. Approve a final distribution name that is not occupied on PyPI.
2. Replace placeholder license and author metadata.
3. Add project URLs and classifiers.
4. Decide whether legacy PoC helpers belong in the distributable SDK.
5. Add CI jobs for build, twine check, clean wheel install, extras install, and import smoke tests.
