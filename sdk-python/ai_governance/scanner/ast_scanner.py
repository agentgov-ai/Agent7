from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any

from ai_governance.scanner.models import (
    build_candidate,
    build_evidence,
    build_model_surface_entry,
)
from ai_governance.scanner.rules import classify_candidate
from ai_governance.scanner.sinks import is_sql_write, match_model_usage, match_sink

logger = logging.getLogger(__name__)

EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "dist", "build",
    "__pycache__", ".pytest_cache", "migrations", ".tox", ".mypy_cache",
    ".eggs", ".ruff_cache",
})

# Decorator attribute names that signal a FastAPI route
_ROUTE_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})

# Common names for router objects
_ROUTER_NAMES = frozenset({"app", "router", "api", "api_router"})

# Patterns for @gov.tool-style decorators
_GOV_TOOL_ATTR = "tool"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scan_codebase(root: str | Path, *, verbose: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int, int]:
    """Scan all ``.py`` files under *root*.

    Returns ``(candidates, model_surface, files_scanned, functions_seen, ignored_helpers)``.
    """
    root = Path(root).resolve()
    py_files = _walk_python_files(root)
    candidates: list[dict[str, Any]] = []
    model_surface: list[dict[str, Any]] = []
    functions_seen = 0
    ignored_helpers = 0

    for fpath in py_files:
        try:
            source = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", fpath, exc)
            continue
        try:
            tree = ast.parse(source, filename=str(fpath))
        except SyntaxError as exc:
            logger.warning("Syntax error in %s: %s", fpath, exc)
            continue

        alias_map = _build_import_map(tree)
        rel_path = _relative(fpath, root)
        module_path = _file_to_module(fpath, root)

        file_result = _visit_file(tree, alias_map, rel_path, module_path, verbose=verbose)
        functions_seen += file_result["functions_seen"]
        ignored_helpers += file_result["ignored_helpers"]
        candidates.extend(file_result["candidates"])
        model_surface.extend(file_result["model_surface"])

    return candidates, model_surface, len(py_files), functions_seen, ignored_helpers


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------

def _walk_python_files(root: Path) -> list[Path]:
    """Collect ``.py`` files, excluding directories in ``EXCLUDED_DIRS``."""
    result: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # prune excluded dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDED_DIRS and not d.endswith(".egg-info")
        ]
        for fn in filenames:
            if fn.endswith(".py"):
                result.append(Path(dirpath) / fn)
    return sorted(result)


# ---------------------------------------------------------------------------
# Import alias resolution
# ---------------------------------------------------------------------------

def _build_import_map(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    """Map local names to their fully-qualified dotted names."""
    alias_map: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                alias_map[local] = tuple(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                if module:
                    alias_map[local] = tuple(module.split(".")) + (alias.name,)
                else:
                    alias_map[local] = (alias.name,)
    return alias_map


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------

def _visit_file(
    tree: ast.Module,
    alias_map: dict[str, tuple[str, ...]],
    rel_path: str,
    module_path: str,
    *,
    verbose: bool = False,
) -> dict[str, Any]:
    """Visit all functions/methods in a single parsed file."""
    candidates: list[dict[str, Any]] = []
    model_surface: list[dict[str, Any]] = []
    functions_seen = 0
    ignored_helpers = 0

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        functions_seen += 1
        func_name = node.name
        param_names = _param_names(node)
        line_start = node.lineno
        line_end = getattr(node, "end_lineno", node.lineno) or node.lineno

        # 1. Check decorators
        decorator_meta = _check_gov_tool_decorator(node)
        route_meta = _check_route_decorator(node)

        # 2. Build local bindings (with X() as name, name = X())
        local_bindings = _build_local_bindings(node, alias_map)

        # 3. Walk body for sink calls and model usage
        sinks_found: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        call_chains: list[str] = []
        file_model_entries: list[dict[str, Any]] = []

        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            resolved = _resolve_call_name(child, alias_map, local_bindings)
            if resolved is None:
                continue

            dotted = ".".join(resolved)

            # Check business sinks
            sink = match_sink(resolved)
            if sink is not None:
                # Special: sql_write_check
                if sink.get("sql_write_check"):
                    sql_str = _first_string_arg(child)
                    if sql_str is not None and not is_sql_write(sql_str):
                        continue  # SELECT etc. — not a write sink
                # Special: open() with read mode
                if resolved == ("open",) or (len(resolved) == 1 and resolved[0] == "open"):
                    if not _is_open_write_mode(child):
                        continue

                sinks_found.append(sink)
                evidence.append(build_evidence(
                    evidence_type="sink_call",
                    detail=dotted,
                    line=getattr(child, "lineno", line_start),
                    file_path=rel_path,
                ))
                call_chains.append(f"{func_name} -> {dotted}")

            # Check model-usage surface
            model_entry = match_model_usage(resolved)
            if model_entry is not None:
                file_model_entries.append(build_model_surface_entry(
                    name=func_name,
                    module_path=module_path,
                    file_path=rel_path,
                    line=getattr(child, "lineno", line_start),
                    provider=model_entry["provider"],
                    call_chain=[f"{func_name} -> {dotted}"],
                ))

        # 4. Add decorator evidence
        if decorator_meta:
            evidence.append(build_evidence(
                evidence_type="decorator",
                detail=f"@*.tool({', '.join(f'{k}={v!r}' for k, v in decorator_meta.items())})",
                line=line_start,
                file_path=rel_path,
            ))

        if route_meta:
            method = route_meta.get("method", "?")
            path = route_meta.get("path", "?")
            evidence.append(build_evidence(
                evidence_type="route",
                detail=f"{method.upper()} {path}",
                line=line_start,
                file_path=rel_path,
            ))

        # 5. Classify
        classification = classify_candidate(
            function_name=func_name,
            param_names=param_names,
            sinks_found=sinks_found,
            decorator_meta=decorator_meta,
            route_meta=route_meta,
        )

        # Add name_heuristic evidence when that's the classification source
        if classification and classification.get("confidence_source") == "name_heuristic" and not evidence:
            evidence.append(build_evidence(
                evidence_type="name_heuristic",
                detail=f"function name '{func_name}' matches risky pattern",
                line=line_start,
                file_path=rel_path,
            ))

        if not classification and not evidence:
            # pure helper — no signals at all
            ignored_helpers += 1
            model_surface.extend(file_model_entries)
            continue

        if not classification:
            # has evidence (e.g. route) but classify returned empty
            # still treat as candidate with defaults
            classification = {
                "suggested_action_type": "unknown",
                "suggested_data_classes": [],
                "suggested_approval_required": False,
                "external_side_effect": False,
                "risk": "low",
                "confidence": 0.50,
                "confidence_source": "name_heuristic",
            }

        candidate = build_candidate(
            name=func_name,
            module_path=module_path,
            file_path=rel_path,
            line_start=line_start,
            line_end=line_end,
            evidence=evidence,
            call_chain=call_chains,
            **classification,
        )
        candidates.append(candidate)
        model_surface.extend(file_model_entries)

    return {
        "candidates": candidates,
        "model_surface": model_surface,
        "functions_seen": functions_seen,
        "ignored_helpers": ignored_helpers,
    }


# ---------------------------------------------------------------------------
# Call-name resolution
# ---------------------------------------------------------------------------

def _resolve_call_name(
    node: ast.Call,
    alias_map: dict[str, tuple[str, ...]],
    local_bindings: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, ...] | None:
    """Extract the dotted name from a ``Call`` node, resolving import aliases
    and local variable bindings (``with X() as name``, ``name = X()``)."""
    parts = _collect_attr_chain(node.func)
    if parts is None:
        return None

    # strip leading "self" / "cls" for method calls
    if parts and parts[0] in ("self", "cls"):
        parts = parts[1:]
    if not parts:
        return None

    root = parts[0]
    if root in alias_map:
        return alias_map[root] + tuple(parts[1:])
    if local_bindings and root in local_bindings:
        return local_bindings[root] + tuple(parts[1:])
    return tuple(parts)


def _collect_attr_chain(node: ast.expr) -> list[str] | None:
    """Walk ``ast.Attribute`` chains to produce ``["a", "b", "c"]``."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        parts.reverse()
        return parts
    return None


# ---------------------------------------------------------------------------
# Local binding resolution
# ---------------------------------------------------------------------------

def _build_local_bindings(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    alias_map: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    """Track local variables bound to constructor calls.

    Handles ``with X(...) as name`` and ``name = X(...)`` so that
    ``name.method()`` can be resolved to ``X.method()``.
    """
    bindings: dict[str, tuple[str, ...]] = {}
    for child in ast.walk(func_node):
        # with X(...) as name
        if isinstance(child, ast.With):
            for item in child.items:
                var = item.optional_vars
                if var is None or not isinstance(var, ast.Name):
                    continue
                ctx = item.context_expr
                if isinstance(ctx, ast.Call):
                    resolved = _collect_attr_chain(ctx.func)
                    if resolved is not None:
                        root = resolved[0]
                        if root in ("self", "cls"):
                            resolved = resolved[1:]
                        if resolved:
                            fq = alias_map.get(resolved[0], (resolved[0],)) + tuple(resolved[1:])
                            bindings[var.id] = fq
        # name = X(...)
        if isinstance(child, ast.Assign):
            if len(child.targets) == 1 and isinstance(child.targets[0], ast.Name):
                if isinstance(child.value, ast.Call):
                    resolved = _collect_attr_chain(child.value.func)
                    if resolved is not None:
                        root = resolved[0]
                        if root in ("self", "cls"):
                            resolved = resolved[1:]
                        if resolved:
                            fq = alias_map.get(resolved[0], (resolved[0],)) + tuple(resolved[1:])
                            bindings[child.targets[0].id] = fq
    return bindings


# ---------------------------------------------------------------------------
# Decorator helpers
# ---------------------------------------------------------------------------

def _check_gov_tool_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any] | None:
    """Check for ``@something.tool(...)`` decorator and extract kwargs."""
    for dec in node.decorator_list:
        call = dec if isinstance(dec, ast.Call) else None
        if call is None:
            continue
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr == _GOV_TOOL_ATTR:
            meta: dict[str, Any] = {}
            for kw in call.keywords:
                if kw.arg and isinstance(kw.value, ast.Constant):
                    meta[kw.arg] = kw.value.value
                elif kw.arg and isinstance(kw.value, ast.List):
                    meta[kw.arg] = [
                        elt.value for elt in kw.value.elts
                        if isinstance(elt, ast.Constant)
                    ]
            return meta if meta else {"_detected": True}
    return None


def _check_route_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any] | None:
    """Check for ``@app.post("/path")`` style FastAPI decorators."""
    for dec in node.decorator_list:
        call = dec if isinstance(dec, ast.Call) else None
        if call is None:
            # bare decorator like @app.get without call — less common for routes
            if isinstance(dec, ast.Attribute) and dec.attr in _ROUTE_METHODS:
                chain = _collect_attr_chain(dec)
                if chain and len(chain) == 2 and chain[0] in _ROUTER_NAMES:
                    return {"method": dec.attr, "path": "?"}
            continue

        func = call.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in _ROUTE_METHODS:
            continue
        chain = _collect_attr_chain(func)
        if not chain or len(chain) != 2:
            continue
        if chain[0] not in _ROUTER_NAMES:
            continue

        # extract path from first positional arg
        path = "?"
        if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
            path = call.args[0].value

        return {"method": func.attr, "path": path}

    return None


# ---------------------------------------------------------------------------
# Argument inspection helpers
# ---------------------------------------------------------------------------

def _first_string_arg(call: ast.Call) -> str | None:
    """Return the first positional string-literal argument, or ``None``."""
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _is_open_write_mode(call: ast.Call) -> bool:
    """Return ``True`` if an ``open(...)`` call uses a write mode."""
    # check second positional arg
    if len(call.args) >= 2:
        mode_node = call.args[1]
        if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
            return any(c in mode_node.value for c in "waxWAX+")
    # check 'mode' keyword
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return any(c in kw.value.value for c in "waxWAX+")
    return False


def _param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract parameter names from a function definition."""
    names: list[str] = []
    args = node.args
    for a in args.posonlyargs + args.args + args.kwonlyargs:
        names.append(a.arg)
    if args.vararg:
        names.append(args.vararg.arg)
    if args.kwarg:
        names.append(args.kwarg.arg)
    return names


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _relative(fpath: Path, root: Path) -> str:
    """Portable relative path with forward slashes."""
    try:
        return fpath.relative_to(root).as_posix()
    except ValueError:
        return fpath.as_posix()


def _file_to_module(fpath: Path, root: Path) -> str:
    """Convert a file path to a dotted module path."""
    try:
        rel = fpath.relative_to(root)
    except ValueError:
        rel = fpath
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)
