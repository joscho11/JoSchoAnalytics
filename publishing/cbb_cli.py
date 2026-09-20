"""CLI for the date-keyed College Basketball daily release contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cbb_daily import cbb_status, publish_card_candidate, publish_result_candidate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m publishing.cbb_cli")
    parser.add_argument("--root", default=None, help="website repository root (defaults to this repository)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("publish-card", publish_card_candidate), ("publish-results", publish_result_candidate)):
        cmd = sub.add_parser(name)
        cmd.add_argument("--artifact", required=True)
        cmd.add_argument("--metadata", required=True)
        cmd.set_defaults(handler=fn)
    sub.add_parser("status").set_defaults(handler=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "status":
            result = cbb_status(root=args.root)
        else:
            result = args.handler(args.artifact, args.metadata, root=args.root)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0
    except Exception as exc:  # CLI boundary: fail closed with a concise error.
        print(f"CBB publication failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
