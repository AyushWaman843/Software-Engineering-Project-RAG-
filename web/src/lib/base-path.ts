/** Must match `basePath` in next.config.ts */
export const BASE_PATH: string = "/scanner";

/** Strip Next.js basePath so browser URL paths match `usePathname()` values. */
export function stripBasePath(pathname: string): string {
  if (!BASE_PATH || BASE_PATH === "/") {
    return pathname || "/";
  }
  if (pathname === BASE_PATH) return "/";
  if (pathname.startsWith(`${BASE_PATH}/`)) {
    return pathname.slice(BASE_PATH.length) || "/";
  }
  return pathname;
}

export function withBasePath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (!BASE_PATH || BASE_PATH === "/") return normalized;
  if (normalized === BASE_PATH || normalized.startsWith(`${BASE_PATH}/`)) {
    return normalized;
  }
  return `${BASE_PATH}${normalized}`;
}

export function appUrl(origin: string, path: string): string {
  return `${origin.replace(/\/$/, "")}${withBasePath(path)}`;
}
