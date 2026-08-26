"use client";

import { useEffect, useState } from "react";
import { captureWebsiteReturnUrl, getWebsiteReturnUrl } from "@/lib/website-return";

/** Resolves where "Back to Website" should go (TrustStack page the user came from). */
export function useWebsiteReturnUrl(): string {
  const [href, setHref] = useState("/");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    captureWebsiteReturnUrl(params.get("from") ?? params.get("return"));
    setHref(getWebsiteReturnUrl());
  }, []);

  return href;
}
