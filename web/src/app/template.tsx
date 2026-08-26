export default function PageTransitionTemplate({ children }: { children: React.ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
