from src.locdex.safety import check_ast_security, is_protected_path, is_safe_path


def test_normal_os_and_requests_imports_are_not_blocked():
    code = "import os\nimport requests\n\ndef f():\n    return os.getenv('X')\n"
    assert check_ast_security(code) == []


def test_dynamic_execution_is_blocked():
    flags = check_ast_security("def f(x):\n    return eval(x)\n")
    assert any("eval" in flag for flag in flags)


def test_shell_true_is_blocked():
    flags = check_ast_security(
        "import subprocess\nsubprocess.run('echo unsafe', shell=True)\n"
    )
    assert any("shell=True" in flag for flag in flags)


def test_path_boundaries(tmp_path):
    assert is_safe_path(str(tmp_path), "src/a.py")
    assert not is_safe_path(str(tmp_path), "../escape.py")
    assert is_protected_path(".git/config")
    assert not is_protected_path("src/app.py")
