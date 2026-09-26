from __future__ import annotations

import json
from pathlib import Path

from platformdirs import user_data_dir

DATA_DIR = Path(user_data_dir("Locdex", "Locdex"))
BUDGET_FILE = DATA_DIR / "usage_metrics.json"


def load_budget() -> dict:
    if BUDGET_FILE.exists():
        try:
            data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"total_spent": 0.0, "local_calls": 0, "cloud_calls": 0}


def save_budget(data: dict) -> None:
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_usage(source: str, prompt: str = "", generated_text: str = "", cost_usd: float | None = None) -> None:
    del prompt, generated_text
    budget = load_budget()
    if source == "local":
        budget["local_calls"] = int(budget.get("local_calls", 0)) + 1
    else:
        budget["cloud_calls"] = int(budget.get("cloud_calls", 0)) + 1
        if cost_usd is not None:
            budget["total_spent"] = float(budget.get("total_spent", 0.0)) + max(0.0, float(cost_usd))
    save_budget(budget)


def get_metrics_report() -> str:
    b = load_budget()
    return (
        "\n--- Locdex Usage Metrics ---\n"
        f"Local Generations: {int(b.get('local_calls', 0))}\n"
        f"Cloud Fallbacks:   {int(b.get('cloud_calls', 0))}\n"
        f"Recorded Cloud Cost: ${float(b.get('total_spent', 0.0)):.4f}\n"
        "----------------------------\n"
    )
