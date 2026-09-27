import sys

from locdex.validator import full_validation, run_sandboxed


def test_run_sandboxed_success():
    """Verify that a safe, fast subprocess executes correctly."""
    res, err = run_sandboxed([sys.executable, "-c", "print('sandbox test')"], timeout=5)
    assert err is None, "Sandbox should not return an error for valid code."
    assert res.returncode == 0
    assert "sandbox test" in res.stdout

def test_run_sandboxed_timeout():
    """Verify that infinite loops or long-running processes are strictly killed."""
    # We tell Python to sleep for 3 seconds, but restrict the sandbox to 1 second
    res, err = run_sandboxed([sys.executable, "-c", "import time; time.sleep(3)"], timeout=1)
    
    assert res is None, "Result should be None when a timeout occurs."
    assert err is not None
    assert "Execution timed out" in err, "Sandbox failed to kill the hanging process."

def test_full_validation_syntax_error():
    """Verify that invalid Python syntax fails the validation gate instantly."""
    bad_code = "def missing_colon() print('this is bad syntax')"
    
    # Run validation on the bad code
    result = full_validation(".", bad_code, "dummy.py")
    
    assert result["all_pass"] is False, "Validation gate incorrectly passed invalid syntax."
    assert result["lint_pass"] is False
    assert "Syntax Error" in result["message"]

def test_run_sandboxed_scrubs_environment():
    """Verify that sensitive API keys are stripped from the execution environment."""
    import os
    
    # Temporarily inject a fake token into the parent environment
    os.environ["GITHUB_TOKEN"] = "fake_secret_token_123"
    
    # Ask the sandbox to execute code that tries to print the environment variable
    code = "import os; print('TOKEN_VALUE=' + str(os.environ.get('GITHUB_TOKEN')))"
    res, err = run_sandboxed([sys.executable, "-c", code], timeout=5)
    
    # Verify the sandbox ran successfully
    assert err is None
    
    # Verify the token is 'None' inside the sandbox (it was successfully scrubbed)
    assert "TOKEN_VALUE=None" in res.stdout, "Sandbox failed to scrub GITHUB_TOKEN from the environment!"
    
    # Cleanup
    del os.environ["GITHUB_TOKEN"]