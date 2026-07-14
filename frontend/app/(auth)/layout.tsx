export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="dark-shift auth-scope relative min-h-screen overflow-hidden"
      data-testid="auth-shell"
      style={{
        background:
          'radial-gradient(1200px 600px at 12% -10%, rgba(34, 211, 238, 0.14), transparent 55%),' +
          'radial-gradient(900px 500px at 92% 0%, rgba(167, 139, 250, 0.13), transparent 60%),' +
          'linear-gradient(180deg, #060913 0%, #080b16 42%, #05070d 100%)',
      }}
    >
      {/* HUD grid overlay */}
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            'linear-gradient(rgba(148, 163, 214, 0.05) 1px, transparent 1px),' +
            'linear-gradient(90deg, rgba(148, 163, 214, 0.05) 1px, transparent 1px)',
          backgroundSize: '56px 56px',
          maskImage: 'radial-gradient(ellipse at center, rgba(0,0,0,0.9), transparent 82%)',
        }}
      />

      {/* Ambient orbs */}
      <div className="pointer-events-none absolute -left-40 top-[-8rem] h-[520px] w-[520px] rounded-full bg-cyan-500/20 blur-[140px]" />
      <div className="pointer-events-none absolute right-[-8rem] top-1/3 h-[440px] w-[440px] rounded-full bg-violet-500/20 blur-[140px]" />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
