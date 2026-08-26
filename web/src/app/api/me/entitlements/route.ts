import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Returns prepaid scan credits for the Bearer user.
 * Uses service role so RLS on user_entitlements does not hide credits.
 */
export async function GET(request: NextRequest) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  const service = process.env.SUPABASE_SERVICE_KEY?.trim();
  if (!url || !anon || !service) {
    return NextResponse.json({ error: "Supabase not configured" }, { status: 503 });
  }

  const auth = request.headers.get("authorization") || "";
  const token = auth.toLowerCase().startsWith("bearer ") ? auth.slice(7).trim() : "";
  if (!token) {
    return NextResponse.json({ prepaid_scans: 0, tier: "free" }, { status: 200 });
  }

  const userClient = createClient(url, anon, {
    global: { headers: { Authorization: `Bearer ${token}` } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: userData, error: userError } = await userClient.auth.getUser(token);
  const userId = userData.user?.id;
  if (userError || !userId) {
    return NextResponse.json({ prepaid_scans: 0, tier: "free" }, { status: 200 });
  }

  const admin = createClient(url, service, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const [{ data: tierData }, { data: entData }] = await Promise.all([
    admin.rpc("get_user_tier", { p_user_id: userId }),
    admin
      .from("user_entitlements")
      .select("scan_credits")
      .eq("user_id", userId)
      .maybeSingle(),
  ]);

  const tier = tierData === "pilot" ? "pilot" : "free";
  const prepaid = Math.max(0, Number(entData?.scan_credits) || 0);

  return NextResponse.json({
    user_id: userId,
    tier,
    prepaid_scans: prepaid,
    scan_credits: prepaid,
  });
}
