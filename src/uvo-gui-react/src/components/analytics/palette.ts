/**
 * One categorical palette for every analytics chart. Each colour is >= 3:1 against the white
 * card background (WCAG 1.4.11); series are additionally labelled directly, never colour-only.
 */
export const CHART_COLORS = [
  '#2563eb', // blue
  '#c2410c', // orange
  '#0f766e', // teal
  '#7c3aed', // violet
  '#be123c', // rose
  '#4d7c0f', // olive
  '#a16207', // ochre
  '#a21caf', // magenta
  '#0369a1', // steel blue
  '#475569', // slate
] as const

/** The residual "Ostatné" bucket is always neutral. */
export const OTHER_COLOR = '#64748b'

export function seriesColor(index: number, key?: string): string {
  if (key === 'other') return OTHER_COLOR
  return CHART_COLORS[index % CHART_COLORS.length]
}
