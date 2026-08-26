import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

// Server-only gate — never enable via NEXT_PUBLIC_* alone (bundle-visible).
const DEMO_ENABLED = process.env.DEMO_AUTO_LOGIN === "1";
const DEMO_EMAIL =
  process.env.DEMO_EMAIL?.trim() ||
  process.env.NEXT_PUBLIC_DEMO_EMAIL?.trim() ||
  "demo@anixai.io";

export async function POST() {
  if (!DEMO_ENABLED) {
    return NextResponse.json({ error: "Demo sign-in is not enabled." }, { status: 404 });
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const serviceKey =
    process.env.SUPABASE_SERVICE_KEY?.trim() ||
    process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();

  if (!url || !serviceKey) {
    return NextResponse.json({ error: "Demo auth is not configured." }, { status: 503 });
  }

  const admin = createClient(url, serviceKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });

  const { data, error } = await admin.auth.admin.generateLink({
    type: "magiclink",
    email: DEMO_EMAIL,
  });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 502 });
  }

  const tokenHash = data.properties?.hashed_token;
  if (!tokenHash) {
    return NextResponse.json({ error: "Could not create demo session token." }, { status: 502 });
  }

  return NextResponse.json({
    ok: true,
    token_hash: tokenHash,
    email: DEMO_EMAIL,
  });
}
