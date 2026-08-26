/**
 * Load key=value pairs from a .env file (no variable expansion).
 */
import fs from "fs";

export function parseEnvFile(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return {};
  const env = {};
  for (const line of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

/** Merge root + web env for Next.js (APP_PASSWORD, API proxy key, Supabase). */
export function nextAuthEnv(projectRoot, webRoot) {
  const rootEnv = parseEnvFile(`${projectRoot}/.env`);
  const webEnv = parseEnvFile(`${webRoot}/.env.local`);
  const apiKey =
    webEnv.INTERNAL_API_KEY ||
    webEnv.API_KEY ||
    rootEnv.INTERNAL_API_KEY ||
    rootEnv.API_KEY ||
    "";
  const appPassword =
    Object.prototype.hasOwnProperty.call(webEnv, "APP_PASSWORD")
      ? webEnv.APP_PASSWORD
      : rootEnv.APP_PASSWORD || "";
  const supabaseUrl =
    webEnv.NEXT_PUBLIC_SUPABASE_URL || rootEnv.SUPABASE_URL || "";
  const supabaseAnon =
    webEnv.NEXT_PUBLIC_SUPABASE_ANON_KEY || rootEnv.SUPABASE_ANON_KEY || "";
  const demoAutoLogin =
    Object.prototype.hasOwnProperty.call(webEnv, "NEXT_PUBLIC_DEMO_AUTO_LOGIN")
      ? webEnv.NEXT_PUBLIC_DEMO_AUTO_LOGIN
      : rootEnv.DEMO_AUTO_LOGIN || "";
  const demoEmail =
    Object.prototype.hasOwnProperty.call(webEnv, "NEXT_PUBLIC_DEMO_EMAIL")
      ? webEnv.NEXT_PUBLIC_DEMO_EMAIL
      : rootEnv.DEMO_EMAIL || "";
  const demoPassword =
    Object.prototype.hasOwnProperty.call(webEnv, "NEXT_PUBLIC_DEMO_PASSWORD")
      ? webEnv.NEXT_PUBLIC_DEMO_PASSWORD
      : rootEnv.DEMO_PASSWORD || "";
  const supabaseServiceKey =
    webEnv.SUPABASE_SERVICE_KEY ||
    rootEnv.SUPABASE_SERVICE_KEY ||
    "";
  return {
    APP_PASSWORD: appPassword,
    INTERNAL_API_KEY: apiKey,
    API_KEY: apiKey,
    NEXT_PUBLIC_SUPABASE_URL: supabaseUrl,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: supabaseAnon,
    NEXT_PUBLIC_DEMO_AUTO_LOGIN: demoAutoLogin,
    NEXT_PUBLIC_DEMO_EMAIL: demoEmail,
    NEXT_PUBLIC_DEMO_PASSWORD: demoPassword,
    SUPABASE_SERVICE_KEY: supabaseServiceKey,
  };
}
