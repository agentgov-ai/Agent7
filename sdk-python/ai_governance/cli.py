from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``agent-governance``."""
    parser = argparse.ArgumentParser(
        prog="agent-governance",
        description="AI Governance SDK — local codebase scanner and utilities",
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_p = subparsers.add_parser(
        "scan",
        help="Scan a Python codebase for governance capability candidates",
    )
    scan_p.add_argument("path", help="Root directory to scan")
    scan_p.add_argument(
        "--output", "-o",
        default="governance-discovery.json",
        help="Output file path (default: governance-discovery.json)",
    )
    scan_p.add_argument(
        "--format", "-f",
        choices=["json", "yaml"],
        default="json",
        dest="fmt",
        help="Output format (default: json)",
    )
    scan_p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed progress",
    )

    upload_p = subparsers.add_parser(
        "upload-discovery",
        help="Upload a governance-discovery.json to the Evidence API",
    )
    upload_p.add_argument("file", help="Path to governance-discovery.json")
    upload_p.add_argument(
        "--api",
        default="http://127.0.0.1:8000",
        help="Evidence API base URL (default: http://127.0.0.1:8000)",
    )
    upload_p.add_argument(
        "--system-id",
        default=None,
        help="Override system_id (default: read from discovery file)",
    )

    args = parser.parse_args(argv)

    if args.command == "scan":
        return _run_scan(args)
    if args.command == "upload-discovery":
        return _run_upload(args)

    parser.print_help()
    return 1


def _run_scan(args: argparse.Namespace) -> int:
    from ai_governance.scanner import (
        format_discovery,
        scan_codebase,
        write_governance_discovery,
    )

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Scanning {root} …")

    candidates, model_surface, files_scanned, functions_seen, ignored = scan_codebase(
        root, verbose=args.verbose,
    )

    discovery = format_discovery(
        candidates=candidates,
        model_surface=model_surface,
        files_scanned=files_scanned,
        functions_seen=functions_seen,
        ignored_helpers_count=ignored,
        root_path=root,
    )

    write_governance_discovery(discovery, args.output, fmt=args.fmt)

    summary = discovery["scan_summary"]
    print(f"Scan complete: {summary['files_scanned']} files, "
          f"{summary['candidates_found']} candidates, "
          f"{summary['model_surface_found']} model-usage entries")
    print(f"  high={summary['high_risk_count']}  "
          f"medium={summary['medium_risk_count']}  "
          f"low={summary['low_risk_count']}")
    print(f"Output: {args.output}")
    return 0


def _run_upload(args: argparse.Namespace) -> int:
    import json
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    fpath = Path(args.file)
    if not fpath.is_file():
        print(f"Error: {fpath} not found", file=sys.stderr)
        return 1

    discovery = json.loads(fpath.read_text(encoding="utf-8"))
    system_id = args.system_id or discovery.get("system_id")
    if not system_id:
        # Derive from scan summary or use filename
        system_id = fpath.stem.replace("governance-discovery", "").strip("-_") or "unknown-system"

    payload = json.dumps({"system_id": system_id, "discovery": discovery}).encode("utf-8")
    url = f"{args.api.rstrip('/')}/discovery/upload"

    try:
        req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        print(f"Error: could not reach {url}: {exc}", file=sys.stderr)
        return 1

    print(f"Upload complete:")
    print(f"  system_id:        {result.get('system_id')}")
    print(f"  upload_id:        {result.get('upload_id')}")
    print(f"  candidates:       {result.get('candidates_stored')}")
    print(f"  reviews carried:  {result.get('reviews_carried_forward', 0)}")
    print(f"  dashboard:        {args.api.rstrip('/')}/ui/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
