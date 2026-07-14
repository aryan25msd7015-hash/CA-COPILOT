/**
 * Futuristic status chip. Keeps original semantic keys but renders
 * cinematic HUD-styled pills with signal dots + monospaced captions.
 */
type ToneClass = string;

const GREEN: ToneClass  = 'bg-emerald-500/12 text-emerald-200 border-emerald-500/30 shadow-[0_0_18px_-6px_rgba(52,211,153,0.55)]';
const BLUE: ToneClass   = 'bg-cyan-500/12  text-cyan-200    border-cyan-500/30  shadow-[0_0_18px_-6px_rgba(34,211,238,0.55)]';
const VIOLET: ToneClass = 'bg-violet-500/12 text-violet-200 border-violet-500/30 shadow-[0_0_18px_-6px_rgba(167,139,250,0.55)]';
const AMBER: ToneClass  = 'bg-amber-500/12 text-amber-200   border-amber-500/30 shadow-[0_0_18px_-6px_rgba(251,191,36,0.55)]';
const ROSE: ToneClass   = 'bg-rose-500/12  text-rose-200    border-rose-500/30  shadow-[0_0_18px_-6px_rgba(251,113,133,0.55)]';
const SLATE: ToneClass  = 'bg-white/[0.06] text-fg-2         border-line';

const DOT_MAP: Record<string, string> = {
  GREEN: 'bg-emerald-400',
  BLUE: 'bg-cyan-400',
  VIOLET: 'bg-violet-400',
  AMBER: 'bg-amber-400',
  ROSE: 'bg-rose-400',
  SLATE: 'bg-fg-3',
};

const TONE: Record<string, { cls: ToneClass; dot: string }> = {
  processed:              { cls: GREEN,  dot: DOT_MAP.GREEN },
  completed:              { cls: GREEN,  dot: DOT_MAP.GREEN },
  approved:               { cls: GREEN,  dot: DOT_MAP.GREEN },
  resolved:               { cls: GREEN,  dot: DOT_MAP.GREEN },
  filed:                  { cls: GREEN,  dot: DOT_MAP.GREEN },
  exact:                  { cls: GREEN,  dot: DOT_MAP.GREEN },
  verified:               { cls: GREEN,  dot: DOT_MAP.GREEN },
  cleared:                { cls: GREEN,  dot: DOT_MAP.GREEN },
  false_positive:         { cls: GREEN,  dot: DOT_MAP.GREEN },
  opted_in:               { cls: GREEN,  dot: DOT_MAP.GREEN },
  ready:                  { cls: GREEN,  dot: DOT_MAP.GREEN },
  better_than_peers:      { cls: GREEN,  dot: DOT_MAP.GREEN },
  risk_low:               { cls: GREEN,  dot: DOT_MAP.GREEN },
  micro:                  { cls: GREEN,  dot: DOT_MAP.GREEN },

  small:                  { cls: BLUE,   dot: DOT_MAP.BLUE },
  purchase:               { cls: VIOLET, dot: DOT_MAP.VIOLET },
  gstr2b:                 { cls: BLUE,   dot: DOT_MAP.BLUE },
  ocr_complete:           { cls: BLUE,   dot: DOT_MAP.BLUE },
  received:               { cls: BLUE,   dot: DOT_MAP.BLUE },
  processing:             { cls: BLUE,   dot: DOT_MAP.BLUE },
  running:                { cls: BLUE,   dot: DOT_MAP.BLUE },
  in_review:              { cls: BLUE,   dot: DOT_MAP.BLUE },
  in_range:               { cls: BLUE,   dot: DOT_MAP.BLUE },
  generating:             { cls: BLUE,   dot: DOT_MAP.BLUE },
  rescanning:             { cls: BLUE,   dot: DOT_MAP.BLUE },
  ready_to_draft:         { cls: BLUE,   dot: DOT_MAP.BLUE },

  medium:                 { cls: VIOLET, dot: DOT_MAP.VIOLET },

  tolerance:              { cls: AMBER,  dot: DOT_MAP.AMBER },
  completed_with_errors:  { cls: AMBER,  dot: DOT_MAP.AMBER },
  ready_provider_missing: { cls: AMBER,  dot: DOT_MAP.AMBER },
  review_required:        { cls: AMBER,  dot: DOT_MAP.AMBER },
  fuzzy:                  { cls: AMBER,  dot: DOT_MAP.AMBER },
  needs_followup:         { cls: AMBER,  dot: DOT_MAP.AMBER },
  risk_medium:            { cls: AMBER,  dot: DOT_MAP.AMBER },

  pending:                { cls: SLATE,  dot: DOT_MAP.SLATE },
  pending_upload:         { cls: SLATE,  dot: DOT_MAP.SLATE },
  queued:                 { cls: SLATE,  dot: DOT_MAP.SLATE },
  waiting_for_ocr:        { cls: SLATE,  dot: DOT_MAP.SLATE },
  draft:                  { cls: SLATE,  dot: DOT_MAP.SLATE },
  dismissed:              { cls: SLATE,  dot: DOT_MAP.SLATE },
  insufficient:           { cls: SLATE,  dot: DOT_MAP.SLATE },

  open:                   { cls: ROSE,   dot: DOT_MAP.ROSE },
  confirmed:              { cls: ROSE,   dot: DOT_MAP.ROSE },
  blocked_no_consent:     { cls: ROSE,   dot: DOT_MAP.ROSE },
  missing_consent:        { cls: ROSE,   dot: DOT_MAP.ROSE },
  unmatched:              { cls: ROSE,   dot: DOT_MAP.ROSE },
  missed:                 { cls: ROSE,   dot: DOT_MAP.ROSE },
  ocr_failed:             { cls: ROSE,   dot: DOT_MAP.ROSE },
  parse_failed:           { cls: ROSE,   dot: DOT_MAP.ROSE },
  failed_validation:      { cls: ROSE,   dot: DOT_MAP.ROSE },
  failed:                 { cls: ROSE,   dot: DOT_MAP.ROSE },
  risk_high:              { cls: ROSE,   dot: DOT_MAP.ROSE },
  worse_than_peers:       { cls: ROSE,   dot: DOT_MAP.ROSE },
};

export default function StatusBadge({ value }: { value?: string }) {
  const label = value || 'unknown';
  const { cls, dot } = TONE[label] || { cls: SLATE, dot: DOT_MAP.SLATE };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] ${cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label.replaceAll('_', ' ')}
    </span>
  );
}
