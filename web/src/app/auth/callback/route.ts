import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { appUrl, stripBasePath } from "@/lib/base-path";

function isRecoveryNext(rawNext: string): boolean {
  const normalized = stripBasePath(
    rawNext.startsWith("/") ? rawNext : `/${rawNext}`,
  );
  return normalized === "/auth/reset-password" || normalized.startsWith("/auth/reset-password");
}

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type");
  const rawNext = searchParams.get("next") ?? "/";
  const recovery =
    type === "recovery" || isRecoveryNext(rawNext);

  const successRedirect = recovery
    ? appUrl(origin, "/auth/reset-password")
    : `${appUrl(origin, "/")}?auth=confirmed`;

  const failRedirect = recovery
    ? `${appUrl(origin, "/auth/reset-password")}?error=link_expired`
    : `${appUrl(origin, "/")}?auth=failed`;

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !supabaseAnon) {
    return NextResponse.redirect(failRedirect);
  }

  let response = NextResponse.redirect(successRedirect);

  const supabase = createServerClient(supabaseUrl, supabaseAnon, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      return NextResponse.redirect(failRedirect);
    }
    return response;
  }

  if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type: type as "recovery" | "signup" | "invite" | "magiclink" | "email_change" | "email",
    });
    if (error) {
      return NextResponse.redirect(failRedirect);
    }
    return response;
  }

  return NextResponse.redirect(failRedirect);
}
