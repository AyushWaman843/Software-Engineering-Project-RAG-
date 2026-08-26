import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";
import { verifyTurnstileToken } from "@/lib/server/turnstile";
import { emailSchema, passwordSchema } from "@/lib/security/schemas";
import { appUrl } from "@/lib/base-path";

/**
 * Server-side signup gate: requires a valid Turnstile token when configured,
 * then creates the auth user via Supabase. Prevents bots from skipping the UI CAPTCHA
 * while still calling our signup endpoint.
 */
export async function POST(request: Request) {
  let body: { email?: string; password?: string; captchaToken?: string } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  const emailCheck = emailSchema.safeParse((body.email || "").trim());
  if (!emailCheck.success) {
    return NextResponse.json(
      { error: emailCheck.error.issues[0]?.message ?? "Invalid email." },
      { status: 400 },
    );
  }
  const passwordCheck = passwordSchema.safeParse(body.password || "");
  if (!passwordCheck.success) {
    return NextResponse.json(
      { error: passwordCheck.error.issues[0]?.message ?? "Invalid password." },
      { status: 400 },
    );
  }

  const forwarded = request.headers.get("x-forwarded-for");
  const ip = forwarded?.split(",")[0]?.trim() || null;
  const captcha = await verifyTurnstileToken(body.captchaToken, ip);
  if (!captcha.ok) {
    return NextResponse.json({ error: captcha.error }, { status: 403 });
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!url || !anon) {
    return NextResponse.json({ error: "Auth is not configured." }, { status: 503 });
  }

  const origin = request.headers.get("origin") || process.env.NEXT_PUBLIC_SITE_URL || "";
  const redirectTo = origin ? appUrl(origin, "/auth/callback") : undefined;

  const supabase = createClient(url, anon, {
    auth: { autoRefreshToken: false, persistSession: false },
  });

  const { data, error } = await supabase.auth.signUp({
    email: emailCheck.data,
    password: passwordCheck.data,
    options: {
      emailRedirectTo: redirectTo,
      captchaToken: body.captchaToken?.trim() || undefined,
    },
  });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 400 });
  }

  if (data.user?.identities?.length === 0) {
    return NextResponse.json({
      status: "already_registered",
      message: "This email is already registered. Sign in with your password instead.",
    });
  }

  if (data.session) {
    return NextResponse.json({
      status: "ok",
      access_token: data.session.access_token,
      refresh_token: data.session.refresh_token,
    });
  }

  return NextResponse.json({
    status: "confirm_email",
    email: emailCheck.data,
    message: `We sent a verification link to ${emailCheck.data}. Open it to activate your account, then sign in here.`,
  });
}
