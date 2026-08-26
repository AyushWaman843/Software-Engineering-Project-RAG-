import { notFound, redirect } from "next/navigation";
import { cookies } from "next/headers";
import { ReportViewGuard } from "@/components/report/ReportViewGuard";
import { fetchReport } from "@/lib/api";
import { createClient } from "@/lib/supabase/server";
import { supabaseConfigured } from "@/lib/supabase/client";

interface ReportPageProps {
  params: Promise<{ id: string }>;
}

export const dynamic = "force-dynamic";

export default async function ReportPage({ params }: ReportPageProps) {
  const { id } = await params;
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.toString();

  let userId: string | undefined;
  let accessToken: string | undefined;
  if (supabaseConfigured()) {
    try {
      const supabase = await createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      userId = session?.user?.id;
      accessToken = session?.access_token;
    } catch {
      userId = undefined;
      accessToken = undefined;
    }
  }

  const data = await fetchReport(id, { cookieHeader, userId, accessToken });

  if (data === "forbidden") {
    redirect("/");
  }

  if (!data) {
    notFound();
  }

  return <ReportViewGuard reportId={id} />;
}
