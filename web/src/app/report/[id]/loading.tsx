import { PageLoader } from "@/components/ui/PageLoader";

export default function ReportLoading() {
  return (
    <PageLoader
      label="Preparing report"
      sublabel="Analyzing compliance assessment"
      showSkeleton
    />
  );
}
