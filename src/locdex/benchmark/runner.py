from __future__ import annotations


def summarize(results: list[dict]) -> dict:
    total = len(results)
    success = sum(1 for r in results if r.get("success"))
    return {"tasks": total, "successes": success, "success_rate": (success / total if total else 0.0)}
