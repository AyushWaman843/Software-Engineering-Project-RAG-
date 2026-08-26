"use client";

import { useCallback, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { clientApiBase, userApiHeaders } from "@/lib/api";
import {
  notifyPremiumUpdated,
  pollPrepaidScanGranted,
  tryClientPrepaidConfirm,
} from "@/lib/payment-poll";
import type { QuotaInfo } from "@/lib/types";
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

function toSummaryData(order: CheckoutOrderResponse): CheckoutSummaryData {
  return {
    checkout_title: order.checkout_title || "Pay to scan a new site",
    checkout_subtitle: order.checkout_subtitle,
    checkout_includes: order.checkout_includes || [],
    price_display: order.price_display,
    currency: order.currency,
    description: order.description,
  };
}

/** Pay ₹299 to run one new scan when free quota is exhausted (includes full report). */
export function usePaidScanCheckout() {
  const { user, session, openAuth } = useAuth();
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryData, setSummaryData] = useState<CheckoutSummaryData | null>(null);
  const pendingOrder = useRef<CheckoutOrderResponse | null>(null);
  const baselinePrepaid = useRef(0);

  const completePrepaid = useCallback(
    async (paymentResponse: RazorpaySuccess) => {
      if (!user) return;

      setVerifying(true);
      await tryClientPrepaidConfirm(user.id, paymentResponse, session?.access_token);

      const granted = await pollPrepaidScanGranted(
        user.id,
        baselinePrepaid.current,
        undefined,
        session?.access_token,
      );
      if (!granted) {
        throw new Error(
          "Payment received but your scan credit is still processing. Refresh and try again, or contact support@dpdpscanner.in.",
        );
      }

      notifyPremiumUpdated();
    },
    [user, session?.access_token],
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
    await completePrepaid(paymentResponse);
  }, [completePrepaid]);

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

    const authHeaders = {
      ...userApiHeaders(user.id, session?.access_token),
      "Content-Type": "application/json",
    };

    try {
      baselinePrepaid.current = 0;
      try {
        const quotaRes = await fetch(`${clientApiBase}/quota`, {
          credentials: "include",
          headers: userApiHeaders(user.id, session?.access_token),
        });
        if (quotaRes.ok) {
          const quota = (await quotaRes.json()) as QuotaInfo;
          baselinePrepaid.current = quota.prepaid_scans ?? quota.scan_credits ?? 0;
        }
      } catch {
        /* non-fatal */
      }

      const orderRes = await fetch(`${clientApiBase}/scan/checkout`, {
        method: "POST",
        credentials: "include",
        headers: authHeaders,
      });
      const orderData = (await orderRes.json()) as CheckoutOrderResponse;

      if (orderRes.status === 401 || orderData.code === "SIGN_IN_REQUIRED") {
        openAuth("signin");
        return;
      }
      if (!orderRes.ok) {
        throw new Error(orderData.error || "Could not start checkout.");
      }
      if (orderData.already_has_quota) {
        notifyPremiumUpdated();
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
  }, [user, openAuth, session?.access_token]);

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
