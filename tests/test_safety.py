from src.locdex.safety import is_protected_path, is_safe_path  # UPDATE IMPORT AT THE TOP

# ... (keep all your existing ast security tests here) ...

def test_safe_path_allowed():
    """Verify that paths strictly inside the workspace are allowed."""
    assert is_safe_path(".", "src/utils/math.py") == True
    assert is_safe_path(".", "generated_code.py") == True
    assert is_safe_path("/mock_project", "/mock_project/src/main.py") == True

def test_path_traversal_blocked():
    """Verify that relative path traversals escaping the workspace are blocked."""
    assert is_safe_path(".", "../../../windows/system32/cmd.exe") == False
    assert is_safe_path(".", "../.ssh/id_rsa") == False

def test_absolute_path_outside_blocked():
    """Verify that absolute paths completely outside the workspace are blocked."""
    import os
    base = os.path.abspath(".")
    parent_dir = os.path.dirname(base)
    # The parent directory is outside the base directory, so it should fail
    assert is_safe_path(base, parent_dir) == False

def test_protected_path_blocked():
    """Verify that sensitive internal repo directories are strictly blocked."""
    assert is_protected_path(".git/hooks/pre-commit") == True
    assert is_protected_path(".github/workflows/deploy.yml") == True
    assert is_protected_path(".env") == True
    assert is_protected_path("venv/Scripts/activate") == True

def test_unprotected_path_allowed():
    """Verify standard project files are not blocked by the protection filter."""
    assert is_protected_path("src/main.py") == False
    assert is_protected_path("README.md") == False
    assert is_protected_path("tests/test_safety.py") == False

def test_argument_injection_blocked():
    """Verify that filenames starting with a hyphen are blocked to prevent CLI injection."""
    assert is_safe_path(".", "-malicious-flag.py") == False
    assert is_safe_path(".", "src/-malicious.py") == False
    assert is_safe_path(".", "--upload-pack") == False
    