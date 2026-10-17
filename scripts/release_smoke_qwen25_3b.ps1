# Run the Qwen2.5-Coder 3B coding-agent release gate on Windows PowerShell.
# Keeps a disposable Git fixture under TEMP for inspection.
param([ValidateRange(1, 12)][int]$MaxSteps = 8)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
foreach ($cmd in @("locdex", "python", "git")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "Required command missing: $cmd"
    }
}
$root = Join-Path ([IO.Path]::GetTempPath()) (
    "locdex-qwen3b-" + [Guid]::NewGuid().ToString("N").Substring(0, 10)
)
New-Item -ItemType Directory -Path $root -Force | Out-Null

$source = @'
def is_even(value: int) -> bool:
    """Whether an integer is even."""
    return value % 2 == 1
'@
$tests = @'
import unittest
from math_utils import is_even

class TestIsEven(unittest.TestCase):
    def test_even(self):
        self.assertIs(is_even(4), True)
    def test_odd(self):
        self.assertIs(is_even(7), False)
    def test_zero(self):
        self.assertIs(is_even(0), True)
    def test_negative_even(self):
        self.assertIs(is_even(-2), True)

if __name__ == "__main__":
    unittest.main()
'@
$sourcePath = Join-Path $root "math_utils.py"
$testPath = Join-Path $root "test_math_utils.py"
[IO.File]::WriteAllText($sourcePath, $source + [Environment]::NewLine, $utf8)
[IO.File]::WriteAllText($testPath, $tests + [Environment]::NewLine, $utf8)
[IO.File]::WriteAllText((Join-Path $root ".gitignore"), "__pycache__/" + [Environment]::NewLine, $utf8)

& git -C $root init --quiet
& git -C $root config user.name "Locdex Smoke Fixture"
& git -C $root config user.email "smoke-fixture@localhost.invalid"
& git -C $root add math_utils.py test_math_utils.py .gitignore
& git -C $root commit --quiet -m "Add deliberately failing arithmetic fixture"
if ($LASTEXITCODE -ne 0) { throw "Fixture Git commit failed." }

Write-Host "[Locdex Smoke] Fixture: $root"
$baseline = & python -m unittest discover -s $root -p test_math_utils.py -v 2>&1 | Out-String
$baselineExit = $LASTEXITCODE
if ($baselineExit -eq 0 -or $baseline -notmatch "FAIL") {
    throw "Expected baseline test failure was not established."
}
$originalTestHash = (Get-FileHash -Path $testPath -Algorithm SHA256).Hash
Write-Host "[Locdex Smoke] Confirmed: baseline test suite fails."

$settings = @(
    "LOCDEX_LLAMA_CONTEXT_TOKENS", "LOCDEX_INFERENCE_TIMEOUT_SECONDS",
    "LOCDEX_CLOUD_ENABLED", "LOCDEX_TELEMETRY_MODE", "LOCDEX_OFFLINE",
    "LOCDEX_NO_UPDATE_CHECK"
)
$before = @{}
foreach ($name in $settings) {
    $before[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
try {
    $env:LOCDEX_LLAMA_CONTEXT_TOKENS = "4096"
    $env:LOCDEX_INFERENCE_TIMEOUT_SECONDS = "600"
    $env:LOCDEX_CLOUD_ENABLED = "false"
    $env:LOCDEX_TELEMETRY_MODE = "off"
    $env:LOCDEX_OFFLINE = "1"
    $env:LOCDEX_NO_UPDATE_CHECK = "1"

    $task = (
        "Fix only math_utils.py: is_even must return True for all even " +
        "integers, including zero and negatives, and False for odd integers. " +
        "Do not change test_math_utils.py or add files. Run " +
        "'python -m unittest discover -s . -p test_math_utils.py -v' " +
        "to verify the correction."
    )
    $taskArgs = @(
        "task", "--repo", $root, "--model", "qwen25-3b",
        "--mode", "local_only", "--sandbox", "workspace-write",
        "--permission-mode", "auto-edit", "--max-steps", "$MaxSteps",
        "--task", $task
    )
    Write-Host "[Locdex Smoke] Running real local Qwen coding-agent task..."
    $start = Get-Date
    & locdex @taskArgs
    $agentExit = $LASTEXITCODE
    $elapsed = [math]::Round(((Get-Date) - $start).TotalSeconds, 1)

    $final = & python -m unittest discover -s $root -p test_math_utils.py -v 2>&1 | Out-String
    $testExit = $LASTEXITCODE
    Write-Host $final
    $unchangedTests = (Get-FileHash -Path $testPath -Algorithm SHA256).Hash -eq $originalTestHash
    $changed = @(& git -C $root diff --name-only)
    $untracked = @(& git -C $root ls-files --others --exclude-standard)
    $onlySource = $changed.Count -eq 1 -and $changed[0] -eq "math_utils.py" -and $untracked.Count -eq 0
    & git -C $root diff -- math_utils.py

    $passed = $agentExit -eq 0 -and $testExit -eq 0 -and $unchangedTests -and $onlySource
    Write-Host "[Locdex Smoke] Agent exit: $agentExit | Tests exit: $testExit | Seconds: $elapsed"
    Write-Host "[Locdex Smoke] Tests untouched: $unchangedTests | Only source changed: $onlySource"
    Write-Host "[Locdex Smoke] Fixture retained: $root"
    if ($passed) {
        Write-Host "[Locdex Smoke] RESULT: PASS — coding agent completed and verification passed."
        exit 0
    }
    Write-Host "[Locdex Smoke] RESULT: FAIL — release gate not met."
    exit 1
} finally {
    foreach ($name in $settings) {
        [Environment]::SetEnvironmentVariable($name, $before[$name], "Process")
    }
}
