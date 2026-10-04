"use strict";

const fs = require("fs");
const path = require("path");
const {
  ensureDir,
  findCompatiblePython,
  run,
  runtimeDir,
  venvLocdex,
  venvPython
} = require("./runtime");

const PYTHON_PACKAGE =
  process.env.LOCDEX_PYTHON_PACKAGE || "locdex==0.3.2a1";

function main() {
  if (process.env.LOCDEX_NPM_SKIP_BOOTSTRAP === "1") {
    console.log("[Locdex] Skipping Python bootstrap (LOCDEX_NPM_SKIP_BOOTSTRAP=1).");
    return;
  }

  const root = runtimeDir();
  ensureDir(root);

  let python = venvPython(root);
  if (!fs.existsSync(python)) {
    const candidate = findCompatiblePython();
    if (!candidate) {
      throw new Error(
        [
          "Locdex requires Python 3.10, 3.11, or 3.12.",
          "Install a compatible Python and reinstall @locdex/cli,",
          "or set LOCDEX_PYTHON to a compatible Python executable."
        ].join(" ")
      );
    }

    console.log(
      `[Locdex] Creating managed Python environment with ${candidate.info.executable}...`
    );
    run(
      candidate.command,
      [...candidate.prefix, "-m", "venv", path.join(root, "venv")]
    );
    python = venvPython(root);
  }

  console.log(`[Locdex] Installing Python core: ${PYTHON_PACKAGE}`);
  run(python, [
    "-m",
    "pip",
    "--disable-pip-version-check",
    "install",
    "--upgrade",
    PYTHON_PACKAGE
  ]);

  const executable = venvLocdex(root);
  if (!fs.existsSync(executable)) {
    throw new Error(
      `Locdex Python package installed but CLI executable is missing: ${executable}`
    );
  }

  run(executable, ["--version"]);

  const marker = {
    npmPackage: "@locdex/cli",
    npmVersion: require("../package.json").version,
    pythonPackage: PYTHON_PACKAGE,
    runtimeDir: root
  };
  fs.writeFileSync(
    path.join(root, "npm-bootstrap.json"),
    JSON.stringify(marker, null, 2),
    "utf8"
  );

  console.log("[Locdex] npm bootstrap complete.");
  console.log("[Locdex] Models and llama.cpp runtime are installed only when you request them.");
}

try {
  main();
} catch (error) {
  console.error(`[Locdex] npm bootstrap failed: ${error.message}`);
  process.exit(1);
}
