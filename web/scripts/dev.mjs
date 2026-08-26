/**
 * Start the full stack with one command:
 *   Python scan API (port 5000) + Next.js UI (port 3000)
 *
 * Next and the API start in parallel. After Next is listening, we pre-compile
 * the home page so the first browser visit is fast.
 */
import { spawn, execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { nextAuthEnv } from "./load-root-env.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(webRoot, "..");
const apiPort = process.env.SCANNER_API_PORT || "5000";
const nextPort = process.env.NEXT_DEV_PORT || "3000";
const apiUrl = `http://127.0.0.1:${apiPort}/health`;
const nextUrl = `http://127.0.0.1:${nextPort}/`;

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

/** Avoid stale dev servers on 3000/5000 (common cause of slow/wrong-port loads on Windows). */
function freePort(port) {
  if (process.platform !== "win32") return;
  try {
    const lines = execSync(`netstat -ano | findstr :${port}`, { encoding: "utf8" }).split(/\r?\n/);
    const pids = new Set();
    for (const line of lines) {
      if (!line.includes("LISTENING")) continue;
      const parts = line.trim().split(/\s+/);
      const pid = parts[parts.length - 1];
      if (pid && pid !== "0" && pid !== String(process.pid)) pids.add(pid);
    }
    for (const pid of pids) {
      try {
        execSync(`taskkill /PID ${pid} /F`, { stdio: "ignore" });
        console.log(`Freed port ${port} (stopped PID ${pid})`);
      } catch {
        /* already gone */
      }
    }
  } catch {
    /* port not in use */
  }
}

function authHeaders(appPassword) {
  if (!appPassword) return {};
  const token = Buffer.from(`:${appPassword}`).toString("base64");
  return { Authorization: `Basic ${token}` };
}

async function waitForApi(maxAttempts = 60) {
  for (let i = 0; i < maxAttempts; i += 1) {
    try {
      const res = await fetch(apiUrl, { signal: AbortSignal.timeout(2000) });
      if (res.ok) return true;
    } catch {
      /* API not ready yet */
    }
    await sleep(400);
  }
  return false;
}

async function waitForNextReady(appPassword, maxAttempts = 90) {
  const headers = authHeaders(appPassword);
  for (let i = 0; i < maxAttempts; i += 1) {
    try {
      const res = await fetch(nextUrl, {
        headers,
        redirect: "manual",
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok || res.status === 307 || res.status === 308) return true;
      if (res.status === 401 && !appPassword) return true;
    } catch (err) {
      if (err?.name === "TimeoutError" || err?.code === "ECONNREFUSED") {
        await sleep(400);
        continue;
      }
    }
    await sleep(400);
  }
  return false;
}

/** First request to / triggers the heavy dev compile — do it before the user opens the browser. */
async function warmHomePage(appPassword) {
  const headers = authHeaders(appPassword);
  const started = Date.now();
  console.log("Pre-compiling home page (first visit)…");
  try {
    const res = await fetch(nextUrl, {
      headers,
      signal: AbortSignal.timeout(180000),
    });
    if (res.ok) {
      console.log(`Home page ready in ${((Date.now() - started) / 1000).toFixed(1)}s`);
      console.log(`Open http://localhost:${nextPort}\n`);
      return;
    }
    console.warn(`Warmup returned HTTP ${res.status}`);
  } catch (err) {
    console.warn("Warmup compile skipped:", err?.message ?? err);
  }
}

function shutdown(apiProcess, nextProcess, code = 0) {
  if (nextProcess && !nextProcess.killed) nextProcess.kill();
  if (apiProcess && !apiProcess.killed) apiProcess.kill();
  process.exit(code);
}

const python = resolvePython();
const authEnv = nextAuthEnv(projectRoot, webRoot);

freePort(nextPort);
freePort(apiPort);

console.log(`Starting scanner API (${python} app.py) on port ${apiPort}…`);
console.log(`Starting Next.js (Turbopack) on http://localhost:${nextPort} …\n`);

const apiProcess = spawn(python, ["app.py"], {
  cwd: projectRoot,
  stdio: "inherit",
  env: { ...process.env, PORT: apiPort, FLASK_DEBUG: "0" },
});

apiProcess.on("error", (err) => {
  console.error("Failed to start Python scanner API:", err.message);
  process.exit(1);
});

const nextArgs = ["next", "dev", "-p", nextPort];
const nextProcess = spawn("npx", nextArgs, {
  cwd: webRoot,
  stdio: "inherit",
  shell: true,
  env: { ...process.env, ...authEnv },
});

nextProcess.on("error", (err) => {
  console.error("Failed to start Next.js:", err.message);
  shutdown(apiProcess, nextProcess, 1);
});

nextProcess.on("exit", (code) => shutdown(apiProcess, null, code ?? 0));

process.on("SIGINT", () => shutdown(apiProcess, nextProcess, 0));
process.on("SIGTERM", () => shutdown(apiProcess, nextProcess, 0));

if (authEnv.APP_PASSWORD) {
  console.log("Site password protection is ON (APP_PASSWORD).");
} else {
  console.warn(
    "Warning: APP_PASSWORD is not set — anyone with the URL can use the scanner.",
  );
}

void (async () => {
  await Promise.all([
    waitForApi().then((ok) => {
      if (ok) console.log("Scanner API ready.");
      else console.warn(`Scanner API did not respond at ${apiUrl} (scans may fail until it is up).`);
    }),
    waitForNextReady(authEnv.APP_PASSWORD).then((ok) => {
      if (!ok) console.warn(`Next.js did not respond on port ${nextPort} in time.`);
    }),
  ]);

  await warmHomePage(authEnv.APP_PASSWORD);
})();
