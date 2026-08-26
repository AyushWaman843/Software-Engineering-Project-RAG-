/** TrustStack Pilot checkout URL (main site). */
export function truststackSubscribeUrl(): string {
  if (typeof window === "undefined") return "/subscribe";
  const origin = window.location.origin;
  // Proxied under TrustStack: /scanner → host /subscribe
  if (window.location.pathname.startsWith("/scanner")) {
    return `${origin}/subscribe`;
  }
  return process.env.NEXT_PUBLIC_TRUSTSTACK_URL
    ? `${process.env.NEXT_PUBLIC_TRUSTSTACK_URL.replace(/\/$/, "")}/subscribe`
    : `${origin}/subscribe`;
}
