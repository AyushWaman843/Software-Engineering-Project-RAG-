import { PageLoader } from "@/components/ui/PageLoader";

export default function RootLoading() {
  return (
    <PageLoader
      label="Loading workspace"
      sublabel="Syncing compliance data"
    />
  );
}
