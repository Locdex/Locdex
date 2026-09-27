from locdex.parser import parse_multi_file_response


def test_multi_file_parsing():
    llm_output = """
    Here is the code you requested:
    
    ### FILE: src/utils/math.py
    ```python
    def add(a, b): return a + b
    ```
    
    ### FILE: tests/test_math.py
    ```
    def test_add(): assert add(1, 2) == 3
    ```
    """
    files = parse_multi_file_response(llm_output)
    
    assert len(files) == 2
    assert files[0]["filepath"] == "src/utils/math.py"
    assert "def add(a, b):" in files[0]["code"]
    assert files[1]["filepath"] == "tests/test_math.py"
    assert "def test_add():" in files[1]["code"]

def test_legacy_fallback_parsing():
    llm_output = """
    FILEPATH: src/legacy.py
    ```python
    print("legacy")
    ```
    """
    files = parse_multi_file_response(llm_output)
    assert len(files) == 1
    assert files[0]["filepath"] == "src/legacy.py"
    assert files[0]["code"] == 'print("legacy")'