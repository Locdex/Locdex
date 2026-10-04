#!/usr/bin/env node
"use strict";

const fs = require("fs");
const { spawnSync } = require("child_process");
const { runtimeDir, venvLocdex } = require("../scripts/runtime");

const executable = venvLocdex(runtimeDir());

if (!fs.existsSync(executable)) {
  console.error(
    [
      "[Locdex] Managed Python runtime is missing.",
      "Reinstall @locdex/cli or run: npm rebuild @locdex/cli",
      "You can override Python discovery with LOCDEX_PYTHON."
    ].join("\n")
  );
  process.exit(1);
}

const result = spawnSync(executable, process.argv.slice(2), {
  stdio: "inherit",
  windowsHide: false,
  env: process.env
});

if (result.error) {
  console.error(`[Locdex] Failed to launch Python core: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
