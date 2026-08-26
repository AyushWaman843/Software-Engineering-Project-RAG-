import type { SupabaseClient } from "@supabase/supabase-js";
import { appUrl } from "@/lib/base-path";
import { emailSchema, passwordSchema } from "@/lib/security/schemas";

export type AuthResult =
  | { status: "ok"; message?: string }
  | { status: "error"; message: string }
  | { status: "confirm_email"; message: string; email: string }
  | { status: "already_registered"; message: string };

function authRedirectUrl(): string {
  if (typeof window === "undefined") return "";
  return appUrl(window.location.origin, "/auth/callback");
}

function mapSignInError(message: string, email: string): AuthResult {
  const lower = message.toLowerCase();
  if (lower.includes("email not confirmed") || lower.includes("not confirmed")) {
    return {
      status: "confirm_email",
      email,
      message: "Confirm your email before signing in. Check your inbox for the verification link.",
    };
  }
  if (lower.includes("invalid login") || lower.includes("invalid credentials")) {
    return { status: "error", message: "Incorrect email or password." };
  }
  return { status: "error", message };
}

export async function signInWithEmail(
  supabase: SupabaseClient,
  email: string,
  password: string,
): Promise<AuthResult> {
  const emailCheck = emailSchema.safeParse(email);
  if (!emailCheck.success) {
    return { status: "error", message: emailCheck.error.issues[0]?.message ?? "Invalid email." };
  }
  if (!password || password.length > 128) {
    return { status: "error", message: "Enter a valid password." };
  }

  const { data, error } = await supabase.auth.signInWithPassword({
    email: emailCheck.data,
    password,
  });

  if (error) {
    return mapSignInError(error.message, email);
  }

  if (!data.session) {
    return { status: "error", message: "Sign in failed. Please try again." };
  }

  return { status: "ok" };
}

export async function signUpWithEmail(
  supabase: SupabaseClient,
  email: string,
  password: string,
  captchaToken?: string,
): Promise<AuthResult> {
  const emailCheck = emailSchema.safeParse(email);
  if (!emailCheck.success) {
    return { status: "error", message: emailCheck.error.issues[0]?.message ?? "Invalid email." };
  }
  const passwordCheck = passwordSchema.safeParse(password);
  if (!passwordCheck.success) {
    return { status: "error", message: passwordCheck.error.issues[0]?.message ?? "Invalid password." };
  }

  // Prefer server-gated signup (Turnstile verified) so bots can't skip the widget
  // and hit Supabase Auth directly through our UI path.
  try {
    const res = await fetch(appUrl(window.location.origin, "/api/auth/signup"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: emailCheck.data,
        password: passwordCheck.data,
        captchaToken: captchaToken || "",
      }),
    });
    const payload = (await res.json()) as {
      status?: string;
      message?: string;
      error?: string;
      access_token?: string;
      refresh_token?: string;
      email?: string;
    };

    if (!res.ok) {
      return { status: "error", message: payload.error || "Sign up failed. Please try again." };
    }

    if (payload.status === "already_registered") {
      return {
        status: "already_registered",
        message: payload.message || "This email is already registered. Sign in instead.",
      };
    }

    if (payload.status === "confirm_email") {
      return {
        status: "confirm_email",
        email: payload.email || emailCheck.data,
        message:
          payload.message ||
          `We sent a verification link to ${emailCheck.data}. Open it to activate your account, then sign in here.`,
      };
    }

    if (payload.status === "ok" && payload.access_token && payload.refresh_token) {
      const { error: sessionError } = await supabase.auth.setSession({
        access_token: payload.access_token,
        refresh_token: payload.refresh_token,
      });
      if (sessionError) {
        return { status: "error", message: sessionError.message };
      }
      return { status: "ok" };
    }

    if (payload.status === "ok") {
      return { status: "ok" };
    }

    return {
      status: "error",
      message: payload.error || payload.message || "Sign up failed. Please try again.",
    };
  } catch {
    // Do not fall back to browser → Supabase signup: that skips server Turnstile.
    return {
      status: "error",
      message: "Sign up is temporarily unavailable. Please try again in a moment.",
    };
  }
}

export async function resendSignupConfirmation(
  supabase: SupabaseClient,
  email: string,
): Promise<AuthResult> {
  const emailCheck = emailSchema.safeParse(email);
  if (!emailCheck.success) {
    return { status: "error", message: emailCheck.error.issues[0]?.message ?? "Invalid email." };
  }

  const { error } = await supabase.auth.resend({
    type: "signup",
    email: emailCheck.data,
    options: {
      emailRedirectTo: authRedirectUrl(),
    },
  });

  if (error) {
    return { status: "error", message: error.message };
  }

  return {
    status: "confirm_email",
    email,
    message: `Verification email sent to ${email}. Check your inbox and spam folder.`,
  };
}

export async function requestPasswordReset(
  supabase: SupabaseClient,
  email: string,
): Promise<AuthResult> {
  const emailCheck = emailSchema.safeParse(email);
  if (!emailCheck.success) {
    return { status: "error", message: emailCheck.error.issues[0]?.message ?? "Invalid email." };
  }

  const redirectTo =
    typeof window !== "undefined"
      ? `${appUrl(window.location.origin, "/auth/callback")}?next=${encodeURIComponent("/auth/reset-password")}`
      : undefined;

  const { error } = await supabase.auth.resetPasswordForEmail(emailCheck.data, {
    redirectTo,
  });

  if (error) {
    return { status: "error", message: error.message };
  }

  return {
    status: "ok",
    message:
      "If an account with that email exists, we've sent a password reset link. Check your inbox and spam folder.",
  };
}

export async function updatePassword(
  supabase: SupabaseClient,
  password: string,
): Promise<AuthResult> {
  const passwordCheck = passwordSchema.safeParse(password);
  if (!passwordCheck.success) {
    return { status: "error", message: passwordCheck.error.issues[0]?.message ?? "Invalid password." };
  }

  const { error } = await supabase.auth.updateUser({ password: passwordCheck.data });
  if (error) {
    return { status: "error", message: error.message };
  }

  return { status: "ok", message: "Password updated. You can sign in with your new password." };
}
