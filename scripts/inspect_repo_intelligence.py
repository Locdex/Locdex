from __future__ import annotations

import argparse
import json

from locdex.intelligence import (
    build_repository_graph,
    find_references,
    find_symbol,
    related_files,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--task", required=True)
    parser.add_argument("--symbol")
    args = parser.parse_args()

    payload = {
        "related_files": related_files(args.repo, args.task, limit=12),
        "graph": build_repository_graph(args.repo),
    }
    if args.symbol:
        payload["symbol"] = find_symbol(args.repo, args.symbol)
        payload["references"] = find_references(args.repo, args.symbol)

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
