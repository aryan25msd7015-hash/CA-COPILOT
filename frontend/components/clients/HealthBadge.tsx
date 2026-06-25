'use client';

interface HealthBadgeProps {
  score: number;
  size?: 'sm' | 'md';
}

export default function HealthBadge({ score, size = 'md' }: HealthBadgeProps) {
  const tier = score >= 75 ? 'green' : score >= 50 ? 'amber' : 'red';
  const config = {
    green: { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500', label: 'Healthy' },
    amber: { bg: 'bg-amber-100', text: 'text-amber-800', dot: 'bg-amber-500', label: 'Needs Attention' },
    red:   { bg: 'bg-red-100',   text: 'text-red-800',   dot: 'bg-red-500',   label: 'High Risk' },
  }[tier];
  const sz = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1';

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-medium ${config.bg} ${config.text} ${sz}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${config.dot}`} />
      {score} — {config.label}
    </span>
  );
}
