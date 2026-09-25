
from src.locdex.validator import _copy_workspace, _stage_candidates


def test_candidate_is_written_only_to_staging_copy(tmp_path):
    real = tmp_path / "real"
    staged = tmp_path / "staged"
    real.mkdir()
    (real / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

    _copy_workspace(str(real), str(staged))
    ok, message, paths = _stage_candidates(
        str(staged), [{"filepath": "app.py", "code": "VALUE = 2\n"}]
    )

    assert ok, message
    assert paths == ["app.py"]
    assert (real / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (staged / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
