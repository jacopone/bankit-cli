"""bankit command line. Data on stdout, one JSON error object on stderr, stable exit codes."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from . import __version__
from .errors import BankitError
from .model import OBSERVATION_FIELDS
from .sources import SOURCES, make_source, route
from .transport import CachingTransport


DISCLAIMER = (
    "Unofficial: not affiliated with Banca d'Italia or the ECB. The data belong to Banca d'Italia and the ECB\n"
    "and remain subject to their terms of use:\n"
    "  https://www.bancaditalia.it/statistiche/condizioni-utilizzo/index.html\n"
    "  https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html"
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # usage errors as JSON, exit 2
        print(json.dumps({"error": "usage", "message": message}), file=sys.stderr)
        sys.exit(2)


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--source", choices=sorted(SOURCES), help="force a source (default: inferred from the key)")
    common.add_argument("--lang", choices=["en", "it"], default="en", help="language of titles (default: en)")
    common.add_argument("--cache-dir", type=Path, help="cache directory (default: $XDG_CACHE_HOME/bankit)")
    common.add_argument("--offline", action="store_true", help="use only cached data, never the network")
    common.add_argument("--refresh", action="store_true", help="ignore cached data and download again")

    p = _Parser(
        prog="bankit",
        description="Banca d'Italia statistics (BDS) and ECB series, one schema. Unofficial client.",
        epilog=DISCLAIMER + "\nExit codes: 0 ok, 2 usage, 3 unsupported, 4 not found, 5 source/network error, 6 offline cache miss.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"bankit {__version__}")
    sub = p.add_subparsers(dest="command", required=True, parser_class=_Parser)

    s = sub.add_parser("search", parents=[common], help="find series by words in their titles")
    s.add_argument("query")
    s.add_argument("--publication", action="append", dest="scope", metavar="CODE",
                   help="limit to a BdI publication (repeatable), e.g. BAM, MFN")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--format", choices=["csv", "json", "jsonl"], default="csv")

    d = sub.add_parser("describe", parents=[common], help="metadata of one series")
    d.add_argument("key")
    d.add_argument("--format", choices=["json"], default="json")

    g = sub.add_parser("get", parents=[common], help="observations of one or more series")
    g.add_argument("keys", nargs="+", metavar="KEY")
    g.add_argument("--start", help="first period, prefix of an ISO date: 2024, 2024-01, 2024-01-15")
    g.add_argument("--end", help="last period, same form as --start")
    g.add_argument("--format", choices=["csv", "json", "jsonl"], default="csv")

    sub.add_parser("sources", help="list available sources")
    return p


def _emit(rows: Iterable[dict[str, object]], fields: Sequence[str], fmt: str) -> None:
    rows = list(rows)
    out = sys.stdout
    if fmt == "json":
        json.dump(rows, out, ensure_ascii=False, indent=2)
        out.write("\n")
    elif fmt == "jsonl":
        for r in rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    else:
        w = csv.DictWriter(out, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})


def _warn(warnings: list[dict[str, object]]) -> None:
    for w in warnings:
        print(json.dumps(w, ensure_ascii=False), file=sys.stderr)


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "sources":
        _emit(({"source": n, "class": c.__name__} for n, c in SOURCES.items()), ["source", "class"], "csv")
        return 0
    transport = CachingTransport(cache_dir=args.cache_dir, offline=args.offline, refresh=args.refresh)
    try:
        if args.command == "search":
            src = make_source(args.source or "bdi", transport, args.lang)
            hits = src.search(args.query, args.scope, args.limit)
            _warn(src.warnings)
            rows = [{**h.to_dict(), **h.extra} for h in hits]
            for r in rows:
                r.pop("extra", None)
            _emit(rows, ["source", "series_key", "title", "publication"], args.format)
        elif args.command == "describe":
            name, bare = route(args.key, args.source)
            src = make_source(name, transport, args.lang)
            info = src.describe(bare)
            _warn(src.warnings)
            json.dump(info.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        elif args.command == "get":
            rows = []
            for key in args.keys:
                name, bare = route(key, args.source)
                src = make_source(name, transport, args.lang)
                rows.extend(o.to_dict() for o in src.get(bare, args.start, args.end))
                _warn(src.warnings)
            _emit(rows, OBSERVATION_FIELDS, args.format)
    except BankitError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        return e.exit_status
    return 0


def main() -> None:
    sys.exit(run())


__all__ = ["main", "run"]
