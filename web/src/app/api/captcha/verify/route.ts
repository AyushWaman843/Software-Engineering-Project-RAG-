import { NextResponse } from "next/server";
import { verifyTurnstileToken } from "@/lib/server/turnstile";

export async function POST(request: Request) {
  let payload: { token?: string } = {};
  try {
    payload = (await request.json()) as { token?: string };
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  const forwarded = request.headers.get("x-forwarded-for");
  const ip = forwarded?.split(",")[0]?.trim() || null;
  const result = await verifyTurnstileToken(payload.token, ip);
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 403 });
  }
  return NextResponse.json({ ok: true });
}
