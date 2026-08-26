/**
 * Host DPDP Scanner for public Cloudflare demo:
 * - No site password (public URL)
 * - Auto sign-in as demo@anixai.io with Pro active
 * - Tunnel port 3000 only (scanner app)
 */
import { spawn, execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { nextAuthEnv } from "./load-root-env.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(webRoot, "..");

const DEMO_EMAIL = "demo@anixai.io";
const DEMO_PASSWORD = "DemoAnix2026!";
const nextPort = "3000";
const apiPort = "5000";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function resolvePython() {
  const venvPy = path.join(projectRoot, "venv", "Scripts", "python.exe");
  if (fs.existsSync(venvPy)) return venvPy;
  return process.platform === "win32" ? "python" : "python3";
}

function freePort(port) {
  if (process.platform !== "win32") return;
  try {
    const lines = execSync(`netstat -ano | findstr :${port}`, { encoding: "utf8" }).split(/\r?\n/);
    for (const line of lines) {
      if (!line.includes("LISTENING")) continue;
      const parts = line.trim().split(/\s+/);
      const pid = parts[parts.length - 1];
      if (pid && pid !== "0") {
        try {
          execSync(`taskkill /PID ${pid} /F`, { stdio: "ignore" });
        } catch {
          /* gone */
        }
      }
    }
  } catch {
    /* not in use */
  }
}

async function waitForUrl(url, maxAttempts = 60) {
  for (let i = 0; i < maxAttempts; i += 1) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (res.ok || res.status === 401) return true;
    } catch {
      /* retry */
    }
    await sleep(500);
  }
  return false;
}

async function waitForTunnelUrl(maxAttempts = 30) {
  const logPath = path.join(process.cwd(), ".demo-tunnel.log");
  for (let i = 0; i < maxAttempts; i += 1) {
    if (fs.existsSync(logPath)) {
      const text = fs.readFileSync(logPath, "utf8");
      const match = text.match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/i);
      if (match) return match[0];
    }
    await sleep(500);
  }
  return null;
}

const authEnv = nextAuthEnv(projectRoot, webRoot);
const demoEnv = {
  ...process.env,
  ...authEnv,
  APP_PASSWORD: "",
  DEMO_AUTO_LOGIN: "1",
  DEMO_EMAIL,
  DEMO_PASSWORD,
  NEXT_PUBLIC_DEMO_AUTO_LOGIN: "1",
  NEXT_PUBLIC_DEMO_EMAIL: DEMO_EMAIL,
  NEXT_PUBLIC_DEMO_PASSWORD: DEMO_PASSWORD,
  SCANNER_API_PORT: apiPort,
  NEXT_DEV_PORT: nextPort,
};

freePort(nextPort);
freePort(apiPort);
try {
  execSync("taskkill /IM cloudflared.exe /F", { stdio: "ignore" });
} catch {
  /* none running */
}

console.log("Ensuring demo account (demo@anixai.io)…");
const python = resolvePython();
try {
  execSync(`${JSON.stringify(python)} create_demo_user.py`, {
    cwd: projectRoot,
    stdio: "inherit",
    env: demoEnv,
    shell: true,
  });
} catch {
  console.warn("Demo user setup had warnings — continuing with existing account.");
}

console.log("\nStarting scanner API + Next.js (demo mode)…");
const apiProcess = spawn(python, ["app.py"], {
  cwd: projectRoot,
  stdio: "inherit",
  env: { ...demoEnv, PORT: apiPort, FLASK_DEBUG: "0" },
});

const nextProcess = spawn("npx", ["next", "dev", "-p", nextPort], {
  cwd: webRoot,
  stdio: "inherit",
  shell: true,
  env: demoEnv,
});

await waitForUrl(`http://127.0.0.1:${apiPort}/health`);
await waitForUrl(`http://127.0.0.1:${nextPort}/scanner`);

console.log("\nWarming up scanner page…");
try {
  await fetch(`http://127.0.0.1:${nextPort}/scanner`, {
    signal: AbortSignal.timeout(120000),
  });
} catch {
  /* continue */
}

const logPath = path.join(webRoot, ".demo-tunnel.log");
if (fs.existsSync(logPath)) fs.unlinkSync(logPath);

console.log("Starting Cloudflare tunnel…");
const tunnelProcess = spawn(
  "cloudflared",
  ["tunnel", "--url", `http://localhost:${nextPort}`, "--logfile", logPath],
  { stdio: "inherit", shell: true },
);

const publicUrl = await waitForTunnelUrl();
if (publicUrl) {
  console.log("\n" + "=".repeat(72));
  console.log("DPDP SCANNER DEMO IS LIVE");
  console.log("=".repeat(72));
  console.log(`\n  Open: ${publicUrl}/scanner`);
  console.log(`\n  Demo account (auto signed-in): ${DEMO_EMAIL}`);
  console.log("  Pro tier active — 5 full scans available");
  console.log("\n  Keep this terminal open. Press Ctrl+C to stop.\n");
} else {
  console.warn("Tunnel started but URL not detected yet — check cloudflared output.");
}

function shutdown(code = 0) {
  if (!tunnelProcess.killed) tunnelProcess.kill();
  if (!nextProcess.killed) nextProcess.kill();
  if (!apiProcess.killed) apiProcess.kill();
  process.exit(code);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
nextProcess.on("exit", (code) => shutdown(code ?? 0));
apiProcess.on("exit", (code) => shutdown(code ?? 0));
