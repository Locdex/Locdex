import os
import tempfile

from locdex.editor import extract_skeleton


def test_extract_skeleton():
    """Verify that the editor extracts only signatures and ignores internal logic."""
    
    # Create a temporary Python file to simulate a repository file
    dummy_code = """
class DataProcessor:
    def process(self, data):
        secret_key = "12345" # This should NOT be extracted
        return True

def standalone_helper(x, y):
    result = x + y # This should NOT be extracted
    return result
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tf:
        tf.write(dummy_code)
        temp_path = tf.name

    try:
        # Run the extractor
        skeleton = extract_skeleton(temp_path)
        
        # Verify the structure is captured
        assert "class DataProcessor:" in skeleton
        assert "def process(self, data):" in skeleton
        assert "def standalone_helper(x, y):" in skeleton
        
        # Verify the internal logic is omitted to save tokens
        assert "secret_key" not in skeleton
        assert "result = x + y" not in skeleton
        
    finally:
        os.remove(temp_path)