"use client";

import { useCallback, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { clientApiBase, userApiHeaders } from "@/lib/api";
import {
  notifyPremiumUpdated,
  pollReportUnlocked,
  tryClientReportUnlock,
} from "@/lib/payment-poll";
import {
  loadRazorpayScript,
  openRazorpayCheckout,
  type CheckoutOrderResponse,
  type RazorpaySuccess,
} from "@/lib/razorpay-checkout";
import {
  CheckoutSummaryModal,
  type CheckoutSummaryData,
} from "@/components/premium/CheckoutSummaryModal";
import { useRouter } from "next/navigation";

function toSummaryData(order: CheckoutOrderResponse): CheckoutSummaryData {
  return {
    checkout_title: order.checkout_title || "Unlock full DPDP report",
    checkout_subtitle: order.checkout_subtitle,
    checkout_includes: order.checkout_includes || [],
    price_display: order.price_display,
    currency: order.currency,
    description: order.description,
  };
}

export function usePremiumCheckout(reportId: string) {
  const { user, session, openAuth } = useAuth();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryData, setSummaryData] = useState<CheckoutSummaryData | null>(null);
  const pendingOrder = useRef<CheckoutOrderResponse | null>(null);

  const completeUnlock = useCallback(
    async (paymentResponse: RazorpaySuccess) => {
      if (!user) return;

      setVerifying(true);
      const unlockResult = await tryClientReportUnlock(
        reportId,
        user.id,
        paymentResponse,
        session?.access_token,
      );

      let unlocked = unlockResult.ok && unlockResult.accessTier === "full";
      if (!unlocked) {
        unlocked = await pollReportUnlocked(
          reportId,
          user.id,
          undefined,
          session?.access_token,
        );
      }
      if (!unlocked) {
        throw new Error(
          "Payment received but unlock is still processing. Refresh the page in a moment or contact support@dpdpscanner.in.",
        );
      }

      notifyPremiumUpdated();
      // Soft-refresh any RSC shells; ReportViewGuard also refetches on the event.
      router.refresh();
    },
    [reportId, user, session?.access_token, router],
  );

  const openRazorpayForOrder = useCallback(async () => {
    const order = pendingOrder.current;
    if (!order?.key_id || !order.order_id) {
      throw new Error("Checkout configuration is incomplete.");
    }

    await loadRazorpayScript();
    const paymentResponse = await openRazorpayCheckout(order);
    setSummaryOpen(false);
    setLoading(false);
    await completeUnlock(paymentResponse);
  }, [completeUnlock]);

  const confirmCheckout = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      await openRazorpayForOrder();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Payment failed.";
      if (message !== "Payment cancelled.") {
        setError(message);
      }
    } finally {
      setLoading(false);
      setVerifying(false);
    }
  }, [openRazorpayForOrder]);

  const cancelCheckout = useCallback(() => {
    if (loading) return;
    setSummaryOpen(false);
    pendingOrder.current = null;
  }, [loading]);

  const checkout = useCallback(async () => {
    if (!user) {
      openAuth("signin");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const orderRes = await fetch(
        `${clientApiBase}/report/${encodeURIComponent(reportId)}/checkout`,
        { method: "POST", credentials: "include", headers: userApiHeaders(user.id, session?.access_token) },
      );
      const orderData = (await orderRes.json()) as CheckoutOrderResponse;

      if (orderRes.status === 401 || orderData.code === "SIGN_IN_REQUIRED") {
        openAuth("signin");
        return;
      }
      if (!orderRes.ok) {
        throw new Error(orderData.error || "Could not start checkout.");
      }
      if (orderData.already_unlocked) {
        notifyPremiumUpdated();
        router.refresh();
        return;
      }

      pendingOrder.current = orderData;
      setSummaryData(toSummaryData(orderData));
      setSummaryOpen(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Payment failed.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [reportId, user, openAuth, session?.access_token, router]);

  const SummaryModal = (
    <CheckoutSummaryModal
      open={summaryOpen}
      data={summaryData}
      loading={loading && summaryOpen}
      onCancel={cancelCheckout}
      onConfirm={() => void confirmCheckout()}
    />
  );

  return {
    checkout,
    loading: loading || verifying,
    verifying,
    error,
    SummaryModal,
  };
}
