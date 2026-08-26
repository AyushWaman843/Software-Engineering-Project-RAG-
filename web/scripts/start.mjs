/**
 * Production stack: Gunicorn API + Next.js (built).
 */
import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { nextAuthEnv } from "./load-root-env.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(webRoot, "..");
const apiPort = process.env.SCANNER_API_PORT || "5000";
const apiUrl = `http://127.0.0.1:${apiPort}/health`;

function resolvePython() {
  const candidates = [
    path.join(projectRoot, "venv", "Scripts", "python.exe"),
    path.join(projectRoot, "venv", "bin", "python"),
    process.platform === "win32" ? "python" : "python3",
  ];
  for (const candidate of candidates) {
    if (candidate.includes(path.sep) && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return candidates[candidates.length - 1];
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForApi(maxAttempts = 90) {
  for (let i = 0; i < maxAttempts; i += 1) {
    try {
      const res = await fetch(apiUrl);
      if (res.ok) return;
    } catch {
      /* API not ready yet */
    }
    await sleep(500);
  }
  throw new Error(`Scanner API did not start at ${apiUrl}`);
}

const python = resolvePython();
console.log(`Starting scanner API (gunicorn) on port ${apiPort}…`);

const apiProcess = spawn(
  python,
  ["-m", "gunicorn", "-c", "gunicorn.conf.py", "app:app"],
  {
    cwd: projectRoot,
    stdio: "inherit",
    env: {
      ...process.env,
      PORT: apiPort,
      FLASK_ENV: process.env.FLASK_ENV || "production",
      FLASK_DEBUG: "0",
    },
  },
);

apiProcess.on("error", (err) => {
  console.error("Failed to start scanner API:", err.message);
  process.exit(1);
});

function shutdown(code = 0) {
  if (!apiProcess.killed) apiProcess.kill();
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

try {
  await waitForApi();
  console.log("Scanner API ready.");
  console.log("Starting Next.js production server on http://localhost:3000 …\n");
} catch (err) {
  console.error(err instanceof Error ? err.message : err);
  shutdown(1);
}

const authEnv = nextAuthEnv(projectRoot, webRoot);
if (authEnv.APP_PASSWORD) {
  console.log("Site password protection is ON (APP_PASSWORD).");
}

const nextProcess = spawn("npx", ["next", "start", "-p", process.env.PORT || "3000"], {
  cwd: webRoot,
  stdio: "inherit",
  shell: true,
  env: { ...process.env, ...authEnv },
});

nextProcess.on("exit", (code) => shutdown(code ?? 0));
