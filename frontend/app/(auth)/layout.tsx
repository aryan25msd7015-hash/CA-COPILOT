export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="relative min-h-screen overflow-hidden bg-[var(--bg-1)]"
      data-testid="auth-shell"
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[420px] bg-[radial-gradient(ellipse_at_top,rgba(11,95,92,0.12),transparent_60%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(18,22,29,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(18,22,29,0.03)_1px,transparent_1px)] bg-[size:48px_48px] opacity-70" />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
