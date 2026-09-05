# FastAPI Middleware Example

This example uses `GovernanceMiddleware` to create request-level traces for a
FastAPI app. It drives the app with `TestClient`, so it generates evidence and
exits without starting a long-running server.

```powershell
conda run python examples\fastapi-app\run_example.py
```
