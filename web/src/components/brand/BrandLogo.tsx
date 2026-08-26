/** Absolute path including basePath — required when proxied via TrustStack /scanner. */
export const LOGO_PATH = "/scanner/dpdp_logo.png";

interface BrandLogoProps {
  /** Display size in pixels (logo is square). */
  size?: number;
  className?: string;
  priority?: boolean;
}

export function BrandLogo({ size = 40, className = "", priority = false }: BrandLogoProps) {
  return (
    // Plain <img>: next/image drops basePath here and 404s behind /scanner.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={LOGO_PATH}
      alt="DPDP Scanner"
      width={size}
      height={size}
      decoding="async"
      fetchPriority={priority ? "high" : "auto"}
      className={`object-contain ${className}`.trim()}
    />
  );
}
