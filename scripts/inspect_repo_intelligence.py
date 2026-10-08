from __future__ import annotations

import argparse
import json

from locdex.intelligence import (
    build_repository_graph,
    build_task_context,
    find_references,
    find_symbol,
    get_reference_context,
    get_symbol_source,
    plan_retrieval,
    related_files,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--task", required=True)
    parser.add_argument("--symbol")
    args = parser.parse_args()

    plan = plan_retrieval(
        args.repo,
        args.task,
        max_files=8,
        source_tokens=1600,
    )
    payload = {
        "retrieval_plan": plan.to_dict(),
        "retrieval_plan_prompt": plan.to_prompt(),
        "related_files": related_files(args.repo, args.task, limit=12),
        "task_context": build_task_context(
            args.repo,
            args.task,
            max_tokens=1600,
            max_files=8,
        ),
        "graph": build_repository_graph(args.repo),
    }
    if args.symbol:
        payload["symbol"] = find_symbol(args.repo, args.symbol)
        payload["symbol_source"] = get_symbol_source(args.repo, args.symbol)
        payload["references"] = find_references(args.repo, args.symbol)
        payload["reference_context"] = get_reference_context(
            args.repo,
            args.symbol,
            context_lines=2,
            limit=12,
        )

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
