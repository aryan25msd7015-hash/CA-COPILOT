import * as React from 'react';
import { cn } from '@/lib/utils';

type Variant = 'default' | 'secondary' | 'outline' | 'destructive';

const variantClass: Record<Variant, string> = {
  default: 'bg-cyan-500/90 text-slate-950 hover:bg-cyan-400',
  secondary: 'bg-slate-700/50 text-slate-100 hover:bg-slate-600/60',
  outline: 'border border-cyan-400/50 bg-transparent text-cyan-100 hover:bg-cyan-500/10',
  destructive: 'bg-rose-500/80 text-white hover:bg-rose-500',
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50',
        variantClass[variant],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = 'Button';
