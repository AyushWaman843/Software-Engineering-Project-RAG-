export interface HistoryItem {
  _report_id: string;
  url: string;
  score: number;
  verdict: string;
  timestamp: string;
  /** "full" = report unlocked (paid or premium), "preview" = free scan only */
  access_tier?: "full" | "preview";
}

export interface AppMeta {
  ai_engine: string;
  scanner_version: string;
  rules_version: string;
  premium_enabled?: boolean;
  premium_free_access?: boolean;
  premium_price_display?: number;
  premium_currency?: string;
  free_scans_per_user?: number;
  anonymous_free_scans?: number;
}

export interface QuotaInfo {
  signed_in: boolean;
  /** Effective TrustStack tier: free | pilot (legacy: pro). */
  tier?: "free" | "pilot" | "pro";
  free_scans_limit: number;
  free_scans_used: number;
  free_scans_remaining: number;
  /** Paid scan slots after pay-before-scan checkout (₹299 full scan). */
  prepaid_scans?: number;
  /** @deprecated Use prepaid_scans — kept for backward compatibility. */
  scan_credits: number;
  /** Pilot: remaining full scans today (0 or 1). */
  pilot_scans_remaining?: number;
  /** True if user has an active TrustStack Pilot subscription. */
  has_pilot?: boolean;
  /** @deprecated Legacy Pro — kept for existing subscribers. */
  pro_scans_remaining?: number;
  /** @deprecated Legacy Pro. */
  has_pro?: boolean;
  can_scan: boolean;
  requires_sign_in: boolean;
  message: string;
  premium_enabled?: boolean;
  premium_free_access?: boolean;
  premium_price_display?: number;
  premium_currency?: string;
  is_premium_user?: boolean;
}

export interface ScanStartResponse {
  job_id: string;
  error?: string;
}

export interface ScanStatusResponse {
  id: string;
  status: "pending" | "running" | "complete" | "error";
  progress?: number;
  message?: string;
  error?: string;
  redirect?: string;
  report_id?: string;
  url?: string;
  score?: number;
  verdict?: string;
}

export interface IndicatorRow {
  key: string;
  indicator: string;
  status: string;
  confidence: string;
  rule: string;
  points: number;
  max_points: number;
}

export interface Finding extends IndicatorRow {
  analysis: string;
  recommendation: string;
  excerpt: string;
}

export interface PremiumMeta {
  indicators_total?: number;
  indicators_locked?: number;
  missing_preview_count?: number;
  /** @deprecated legacy field */
  summary_rows_total?: number;
  /** @deprecated legacy field */
  summary_rows_locked?: number;
  findings_total: number;
  pdf_locked: boolean;
  price_display?: number;
  currency?: string;
}

export interface ReportContext {
  report: Record<string, unknown>;
  report_id: string;
  score: number;
  verdict: string;
  verdict_class: string;
  score_class: string;
  rows: IndicatorRow[];
  missing_indicators?: IndicatorRow[];
  discovered_policy_pages?: Record<string, string>;
  findings: Finding[];
  score_breakdown: Record<string, number>;
  rule_citations: Record<string, string>;
  analysis_details: Record<string, unknown>;
  ai_engine: string;
  policy_extraction_warning: boolean;
  prompt_injection_detected?: string[];
  scanner_version: string;
  rules_version: string;
  access_tier?: "preview" | "full";
  /** high | medium | low — present on LLM-scored reports only */
  confidence_label?: "high" | "medium" | "low" | null;
  average_confidence?: number | null;
  premium?: PremiumMeta;
}

export type InputMode = "url" | "pdf";

export interface UrlScanPayload {
  input_mode: "url";
  url: string;
  privacy_url: string;
  terms_url: string;
  cookie_url: string;
}
