export default function PageHeader({ title, subtitle, actions, eyebrow }: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        {eyebrow && (
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
            {eyebrow}
          </p>
        )}
        <h1 className="mt-1 font-display text-[1.85rem] font-semibold leading-tight tracking-tight text-[var(--fg-0)] sm:text-[2.1rem]">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-2 max-w-3xl text-[15px] leading-6 text-[var(--fg-2)]">
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
