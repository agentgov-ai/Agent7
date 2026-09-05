from __future__ import annotations

from typing import Any

from ai_governance.core import fingerprint, sanitize

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
except ModuleNotFoundError as exc:
    raise ImportError(
        "FastAPI middleware adapter requires the optional 'fastapi' or 'starlette' package. "
        "Install it with: pip install fastapi"
    ) from exc


class GovernanceMiddleware(BaseHTTPMiddleware):
    """Create a governance request trace for each incoming ASGI request."""

    def __init__(
        self,
        app: Any,
        *,
        governance_client: Any,
        request_id_header: str = "x-request-id",
        session_header: str | None = None,
        user_header: str | None = None,
        name_prefix: str = "http",
    ) -> None:
        super().__init__(app)
        self.governance_client = governance_client
        self.request_id_header = request_id_header.lower() if request_id_header else None
        self.session_header = session_header.lower() if session_header else None
        self.user_header = user_header.lower() if user_header else None
        self.name_prefix = name_prefix

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        route = _route_template(request)
        method = request.method.upper()
        request_id = _header(request, self.request_id_header)
        session_value = _header(request, self.session_header)
        user_value = _header(request, self.user_header)
        session_id = fingerprint(session_value) if session_value is not None else (request_id or self.governance_client.session_id)
        user_id_hash = fingerprint(user_value) if user_value is not None else None
        attributes = {
            "http.method": method,
            "http.route": route,
        }
        if request_id is not None:
            attributes["request_id"] = sanitize(request_id)
        if session_value is not None:
            attributes["session_header_hash"] = fingerprint(session_value)
        if user_value is not None:
            attributes["user_header_hash"] = fingerprint(user_value)

        context = self.governance_client.request_context(
            name=f"{self.name_prefix}:{method} {route}",
            session_id=session_id,
            user_id_hash=user_id_hash,
            attributes=attributes,
        )
        context.__enter__()
        try:
            response = await call_next(request)
            context.status_code = getattr(response, "status_code", None)
            context.attributes["http.route"] = _route_template(request)
            context.__exit__(None, None, None)
            return response
        except Exception as exc:
            context.status_code = 500
            context.attributes["http.route"] = _route_template(request)
            context.__exit__(type(exc), exc, exc.__traceback__)
            raise


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        return str(route_path)
    return str(request.scope.get("path") or request.url.path)


def _header(request: Request, header_name: str | None) -> str | None:
    if not header_name:
        return None
    value = request.headers.get(header_name)
    return str(value) if value is not None else None
