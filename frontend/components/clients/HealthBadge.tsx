'use client';

interface HealthBadgeProps {
  score: number;
  size?: 'sm' | 'md';
}

export default function HealthBadge({ score, size = 'md' }: HealthBadgeProps) {
  const tier = score >= 75 ? 'green' : score >= 50 ? 'amber' : 'red';
  const config = {
    green: {
      cls: 'bg-emerald-500/12 text-emerald-200 border-emerald-500/30 shadow-[0_0_18px_-6px_rgba(52,211,153,0.55)]',
      dot: 'bg-emerald-400',
      label: 'Healthy',
    },
    amber: {
      cls: 'bg-amber-500/12 text-amber-200 border-amber-500/30 shadow-[0_0_18px_-6px_rgba(251,191,36,0.55)]',
      dot: 'bg-amber-400',
      label: 'Watch',
    },
    red: {
      cls: 'bg-rose-500/12 text-rose-200 border-rose-500/30 shadow-[0_0_18px_-6px_rgba(251,113,133,0.55)]',
      dot: 'bg-rose-400',
      label: 'High Risk',
    },
  }[tier];
  const sz =
    size === 'sm'
      ? 'text-[10px] px-2 py-0.5 gap-1.5'
      : 'text-xs px-3 py-1 gap-2';

  return (
    <span
      data-testid={`health-badge-${tier}`}
      className={`inline-flex items-center rounded-full border font-mono font-semibold uppercase tracking-[0.12em] ${config.cls} ${sz}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      <span className="font-sans font-semibold text-fg-0">{score}</span>
      <span className="text-fg-2">·</span>
      <span>{config.label}</span>
    </span>
  );
}
