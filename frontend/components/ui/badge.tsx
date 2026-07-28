import * as React from 'react';
import { cn } from '@/lib/utils';

type Variant = 'low' | 'medium' | 'high' | 'critical' | 'neutral';

const styles: Record<Variant, string> = {
  low: 'bg-emerald-500/20 text-emerald-200 border-emerald-400/40',
  medium: 'bg-amber-500/20 text-amber-200 border-amber-400/40',
  high: 'bg-orange-500/20 text-orange-200 border-orange-400/40',
  critical: 'bg-rose-500/20 text-rose-200 border-rose-400/40',
  neutral: 'bg-slate-500/20 text-slate-200 border-slate-400/40',
};

export function Badge({
  className,
  variant = 'neutral',
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: Variant }) {
  return (
    <span
      className={cn('inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium uppercase', styles[variant], className)}
      {...props}
    />
  );
}
