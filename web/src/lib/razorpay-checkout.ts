/** Shared Razorpay Standard Checkout opener. */

export interface RazorpayCheckoutOrder {
  key_id?: string;
  order_id?: string;
  amount?: number;
  currency?: string;
  name?: string;
  description?: string;
  razorpay_notes?: Record<string, string>;
}

export interface RazorpaySuccess {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

export interface RazorpaySubscriptionCheckout {
  key_id?: string;
  subscription_id?: string;
  name?: string;
  description?: string;
  razorpay_notes?: Record<string, string>;
}

export interface RazorpaySubscriptionSuccess {
  razorpay_payment_id: string;
  razorpay_subscription_id: string;
  razorpay_signature: string;
}

interface RazorpayInstance {
  open: () => void;
  on: (event: string, handler: (response: { error?: { description?: string } }) => void) => void;
}

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => RazorpayInstance;
  }
}

export function loadRazorpayScript(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Razorpay is only available in the browser."));
  }
  if (window.Razorpay) return Promise.resolve();

  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.crossOrigin = "anonymous";
    script.referrerPolicy = "strict-origin-when-cross-origin";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Razorpay checkout."));
    document.body.appendChild(script);
  });
}

/** Opens Razorpay popup; description + notes surface on Razorpay's payment form. */
export function openRazorpayCheckout(order: RazorpayCheckoutOrder): Promise<RazorpaySuccess> {
  return new Promise((resolve, reject) => {
    const Razorpay = window.Razorpay;
    if (!Razorpay || !order.key_id || !order.order_id) {
      reject(new Error("Checkout configuration is incomplete."));
      return;
    }

    const rzp = new Razorpay({
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      name: order.name || "DPDP Scanner",
      description: order.description || "DPDP compliance report",
      order_id: order.order_id,
      notes: order.razorpay_notes || {},
      theme: { color: "#FF7A18" },
      handler: (response: RazorpaySuccess) => resolve(response),
      modal: {
        ondismiss: () => reject(new Error("Payment cancelled.")),
      },
    });

    rzp.on("payment.failed", (response) => {
      reject(new Error(response.error?.description || "Payment failed."));
    });
    rzp.open();
  });
}

/** Opens Razorpay subscription checkout (legacy; Pilot is purchased on TrustStack). */
export function openRazorpaySubscriptionCheckout(
  checkout: RazorpaySubscriptionCheckout,
): Promise<RazorpaySubscriptionSuccess> {
  return new Promise((resolve, reject) => {
    const Razorpay = window.Razorpay;
    if (!Razorpay || !checkout.key_id || !checkout.subscription_id) {
      reject(new Error("Subscription checkout configuration is incomplete."));
      return;
    }

    const rzp = new Razorpay({
      key: checkout.key_id,
      subscription_id: checkout.subscription_id,
      name: checkout.name || "DPDP Scanner",
      description: checkout.description || "TrustStack Pilot",
      notes: checkout.razorpay_notes || {},
      theme: { color: "#FF7A18" },
      handler: (response: RazorpaySubscriptionSuccess) => resolve(response),
      modal: {
        ondismiss: () => reject(new Error("Payment cancelled.")),
      },
    });

    rzp.on("payment.failed", (response) => {
      reject(new Error(response.error?.description || "Payment failed."));
    });
    rzp.open();
  });
}

export type CheckoutOrderResponse = RazorpayCheckoutOrder & {
  error?: string;
  code?: string;
  already_unlocked?: boolean;
  already_has_quota?: boolean;
  checkout_title?: string;
  checkout_subtitle?: string;
  checkout_includes?: string[];
  price_display?: number;
  original_price_display?: number;
  discount_percent?: number;
};

export type ProCheckoutResponse = RazorpaySubscriptionCheckout & {
  ok?: boolean;
  error?: string;
  code?: string;
  checkout_mode?: "order" | "subscription";
  order_id?: string;
  amount?: number;
  checkout_title?: string;
  checkout_subtitle?: string;
  checkout_includes?: string[];
  price_display?: number;
  original_price_display?: number;
  discount_percent?: number;
  currency?: string;
  status?: string;
  plan_id?: string;
};
