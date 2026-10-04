"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const SUPPORTED_MINORS = new Set([10, 11, 12]);

function runtimeDir() {
  if (process.env.LOCDEX_NPM_RUNTIME_DIR) {
    return path.resolve(process.env.LOCDEX_NPM_RUNTIME_DIR);
  }
  if (process.platform === "win32" && process.env.LOCALAPPDATA) {
    return path.join(process.env.LOCALAPPDATA, "Locdex", "npm-runtime");
  }
  return path.join(os.homedir(), ".locdex", "npm-runtime");
}

function venvPython(root = runtimeDir()) {
  return process.platform === "win32"
    ? path.join(root, "venv", "Scripts", "python.exe")
    : path.join(root, "venv", "bin", "python");
}

function venvLocdex(root = runtimeDir()) {
  return process.platform === "win32"
    ? path.join(root, "venv", "Scripts", "locdex.exe")
    : path.join(root, "venv", "bin", "locdex");
}

function candidatePythons() {
  const candidates = [];
  if (process.env.LOCDEX_PYTHON) {
    candidates.push({ command: process.env.LOCDEX_PYTHON, prefix: [] });
  }

  if (process.platform === "win32") {
    candidates.push(
      { command: "py", prefix: ["-3.11"] },
      { command: "py", prefix: ["-3.12"] },
      { command: "py", prefix: ["-3.10"] },
      { command: "python", prefix: [] },
      { command: "python3", prefix: [] }
    );
  } else {
    candidates.push(
      { command: "python3.11", prefix: [] },
      { command: "python3.12", prefix: [] },
      { command: "python3.10", prefix: [] },
      { command: "python3", prefix: [] },
      { command: "python", prefix: [] }
    );
  }
  return candidates;
}

function probePython(candidate) {
  const code = [
    "import json, sys",
    "print(json.dumps({'major':sys.version_info.major,'minor':sys.version_info.minor,'executable':sys.executable}))"
  ].join(";");

  const result = spawnSync(
    candidate.command,
    [...candidate.prefix, "-c", code],
    { encoding: "utf8", windowsHide: true }
  );
  if (result.status !== 0 || !result.stdout) {
    return null;
  }

  try {
    const info = JSON.parse(result.stdout.trim());
    if (info.major !== 3 || !SUPPORTED_MINORS.has(info.minor)) {
      return null;
    }
    return { ...candidate, info };
  } catch {
    return null;
  }
}

function findCompatiblePython() {
  for (const candidate of candidatePythons()) {
    const found = probePython(candidate);
    if (found) return found;
  }
  return null;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: options.stdio || "inherit",
    encoding: "utf8",
    windowsHide: true,
    env: { ...process.env, ...(options.env || {}) }
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const rendered = [command, ...args].join(" ");
    throw new Error(`Command failed (${result.status}): ${rendered}`);
  }
  return result;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

module.exports = {
  SUPPORTED_MINORS,
  candidatePythons,
  ensureDir,
  findCompatiblePython,
  probePython,
  run,
  runtimeDir,
  venvLocdex,
  venvPython
};
