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


### Show the Python bootstrap installer progress

npm hides some lifecycle-script output by default. For full stage messages and pip's real download percentages, install in a foreground terminal:

```powershell
npm install -g @locdex/cli --foreground-scripts --loglevel=info
```

Locdex reports stages for Python environment creation, Python package installation, and CLI verification. Percentages are shown for wheel transfers only when pip knows the total bytes; we do not synthesize a misleading total percentage for environment setup.


## Registry release checklist

The scoped package is published under the `@locdex` npm organization. The organization must be created in npm's dashboard by an authorized owner; GitHub organization membership alone does not grant npm ownership.

1. Confirm the corresponding Python version (`locdex==1.4.0a1`) is available on PyPI. The npm postinstall requires it; publishing npm first produces a broken user install.
2. Run `npm run check` and `npm pack --dry-run --ignore-scripts` from this directory. Inspect the tarball file listing before publishing.
3. Verify `npm whoami` identifies a maintainer authorized to publish under `@locdex`, and enable npm two-factor authentication.
4. Publish the prerelease using `npm publish --access public --tag next`. The `next` dist-tag keeps this alpha off npm's default `latest` installation path until general-release acceptance tests succeed.
5. Test a fresh installation with `npm install -g @locdex/cli@next --foreground-scripts --loglevel=info`, and confirm `locdex --version` and `locdex model list` work.

Do not publish from a checkout containing secrets, and never put npm auth tokens in this repository. npm package publication requires interactive account authorization and is distinct from preparing this source tree.
