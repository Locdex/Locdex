import re

MULTI_FILE_PROMPT = (
    "\nPlease output your response using the following format for one or more files.\n"
    "For EACH file you want to create or modify, use this exact structure:\n\n"
    "### FILE: path/to/filename.py\n"
    "```python\n"
    "# code goes here\n"
    "```\n"
)

def parse_multi_file_response(text: str) -> list[dict]:
    files = []
    pattern = r"###\s*FILE:\s*([^\n]+)\n.*?```(?:python)?\s*(.*?)```"
    matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
    for match in matches:
        filepath = match.group(1).strip()
        code = match.group(2).strip()
        files.append({"filepath": filepath, "code": code})
    if not files:
        path_match = re.search(r"(?:FILEPATH:|Targeting:?)\s*([a-zA-Z0-9_\-\./\\]+\.py)", text, re.IGNORECASE)
        filepath = path_match.group(1).strip() if path_match else "generated_code.py"
        code_match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
        code = code_match.group(1).strip() if code_match else text.strip()
        if code:
            files.append({"filepath": filepath, "code": code})
    return files
