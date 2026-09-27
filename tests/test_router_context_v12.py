from locdex import router


def test_router_passes_context_as_context(monkeypatch, tmp_path):
    captured = {}

    def fake_local(task, system="", context=None, **kwargs):
        captured["context"] = context
        return {"status": "completed", "summary": "done", "confidence": 0.9}

    monkeypatch.setattr(router, "run_local_with_confidence", fake_local)

    context = {"repo_path": str(tmp_path), "system_prompt": "important context"}
    result = router.route_task("make change", "general", context, {})

    assert captured["context"] is context
    assert result["source"] == "local"
    assert result["result"]["status"] == "completed"
