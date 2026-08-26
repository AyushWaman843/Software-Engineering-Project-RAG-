import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { withBasePath } from "@/lib/base-path";
import { applySecurityHeaders } from "@/lib/security/headers";

// Server-only secrets — never use NEXT_PUBLIC_ for these (see lib/api.ts, middleware).
const APP_PASSWORD = process.env.APP_PASSWORD?.trim();
const API_KEY = (process.env.INTERNAL_API_KEY || process.env.API_KEY)?.trim();
const IS_DEV = process.env.NODE_ENV !== "production";

function checkBasicAuth(header: string, password: string): boolean {
  if (!header.startsWith("Basic ")) return false;
  try {
    const decoded = atob(header.slice(6));
    const colon = decoded.indexOf(":");
    const pass = colon >= 0 ? decoded.slice(colon + 1) : decoded;
    return pass === password;
  } catch {
    return false;
  }
}

function redirectToHttps(request: NextRequest): NextResponse | null {
  if (IS_DEV) return null;

  const forwardedProto = request.headers.get("x-forwarded-proto");
  if (forwardedProto !== "http") return null;

  const url = request.nextUrl.clone();
  url.protocol = "https:";
  return NextResponse.redirect(url, 308);
}

function isApiPath(pathname: string): boolean {
  return pathname.startsWith("/api") || pathname.startsWith("/scanner/api");
}

/** TrustStack/server rewrites may hit Next on localhost without browser Basic auth.
 * Never trust Host alone (spoofable). Prefer a shared secret header; otherwise only
 * skip when clearly local AND not arriving via an edge/tunnel forwarded IP.
 */
function isInternalProxyRequest(request: NextRequest): boolean {
  const proxySecret = process.env.INTERNAL_PROXY_SECRET?.trim();
  if (proxySecret) {
    return request.headers.get("x-anix-internal-proxy") === proxySecret;
  }

  const fromEdge = Boolean(
    request.headers.get("cf-connecting-ip") ||
      request.headers.get("x-forwarded-for") ||
      request.headers.get("x-real-ip"),
  );
  if (fromEdge) return false;

  const host = (request.headers.get("host") || "").toLowerCase();
  return host.startsWith("127.0.0.1") || host.startsWith("localhost");
}

export async function middleware(request: NextRequest) {
  const httpsRedirect = redirectToHttps(request);
  if (httpsRedirect) {
    applySecurityHeaders(httpsRedirect, IS_DEV);
    return httpsRedirect;
  }

  if (APP_PASSWORD && !isInternalProxyRequest(request)) {
    const auth = request.headers.get("authorization");
    if (!auth || !checkBasicAuth(auth, APP_PASSWORD)) {
      const response = new NextResponse("Authentication required", {
        status: 401,
        headers: {
          "WWW-Authenticate": 'Basic realm="DPDP Scanner - password required"',
        },
      });
      applySecurityHeaders(response, IS_DEV);
      return response;
    }
  }

  const { pathname } = request.nextUrl;

  if (pathname === "/" || pathname === "") {
    const url = request.nextUrl.clone();
    url.pathname = withBasePath("/");
    const response = NextResponse.redirect(url);
    applySecurityHeaders(response, IS_DEV);
    return response;
  }

  if (pathname.startsWith("/auth/") && !pathname.startsWith(withBasePath("/auth/"))) {
    const url = request.nextUrl.clone();
    url.pathname = withBasePath(pathname);
    const response = NextResponse.redirect(url);
    applySecurityHeaders(response, IS_DEV);
    return response;
  }

  const requestHeaders = new Headers(request.headers);
  if (isApiPath(pathname) && API_KEY) {
    requestHeaders.set("X-API-Key", API_KEY);
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  const cookieJar = NextResponse.next();
  if (supabaseUrl && supabaseAnon) {
    const supabase = createServerClient(supabaseUrl, supabaseAnon, {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieJar.cookies.set(name, value, options);
          });
        },
      },
    });
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (isApiPath(pathname)) {
      // Never trust a client-supplied X-User-Id — spoofable.
      requestHeaders.delete("X-User-Id");
      const incomingAuth = request.headers.get("Authorization")?.trim() || "";
      const incomingBearer = incomingAuth.toLowerCase().startsWith("bearer ")
        ? incomingAuth.slice(7).trim()
        : "";
      // Prefer the browser JWT (hydration-fresh) over a possibly stale cookie session.
      const token =
        incomingBearer && incomingBearer !== API_KEY
          ? incomingBearer
          : session?.access_token || "";
      if (token) {
        requestHeaders.set("Authorization", `Bearer ${token}`);
        if (session?.user?.id && token === session.access_token) {
          // Metadata only; Flask must verify the Bearer JWT.
          requestHeaders.set("X-User-Id", session.user.id);
        }
      } else {
        requestHeaders.delete("Authorization");
      }
    }
  }

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  cookieJar.cookies.getAll().forEach(({ name, value }) => {
    response.cookies.set(name, value);
  });

  if (pathname.startsWith("/report/")) {
    response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, private");
    response.headers.set("Pragma", "no-cache");
  }

  applySecurityHeaders(response, IS_DEV);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
