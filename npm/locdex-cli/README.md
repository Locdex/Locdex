# @locdex/cli

npm bootstrapper and launcher for the Python Locdex coding-agent runtime.

## Install

```bash
npm install -g @locdex/cli
locdex --version
locdex model list
```

The npm package creates a Locdex-owned Python virtual environment and installs the matching Python `locdex` package there. It does **not** rewrite the Locdex runtime in Node.js.

## Requirements

- Node.js 18+
- Python 3.10, 3.11, or 3.12

Python discovery can be overridden:

```bash
LOCDEX_PYTHON=/path/to/python npm install -g @locdex/cli
```

On Windows PowerShell:

```powershell
$env:LOCDEX_PYTHON = "C:\Python311\python.exe"
npm install -g @locdex/cli
```

## Runtime and models

The npm postinstall does not download a model or install `llama-cpp-python`. Those remain explicit user choices:

```bash
locdex runtime install --backend auto
locdex model list
locdex model install qwen25-7b
locdex model use qwen25-7b
```

## Development/testing override

Before the Python package is published, the wrapper can install a local path, Git URL, wheel, or alternate pip requirement:

```bash
LOCDEX_PYTHON_PACKAGE=/path/to/Locdex npm install -g ./npm/locdex-cli
```

To validate/package the npm wrapper without creating the managed Python environment:

```bash
LOCDEX_NPM_SKIP_BOOTSTRAP=1 npm install
npm run check
npm pack --dry-run --ignore-scripts
```

The npm wrapper and Python package versions should be released together.
