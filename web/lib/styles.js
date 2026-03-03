// ── Shared style constants ─────────────────────────────────────────────────────
// Usage: <div style={{ ...S.statBox, minWidth: 140 }}>
// All color tokens come from CSS vars defined in app/layout.jsx (:root block).

export const S = {
  // ── Layout ──────────────────────────────────────────────────────────────────
  pageWrapper: {
    maxWidth: 1280,
    margin: '0 auto',
    padding: '40px 40px 80px',
  },

  sectionHeading: {
    fontSize: 20,
    fontWeight: 700,
    fontFamily: "'Fraunces', serif",
    color: 'var(--ink)',
    marginBottom: 16,
    letterSpacing: '-0.01em',
  },

  divider: {
    border: 'none',
    borderTop: '1px solid var(--rule)',
    margin: '32px 0',
  },

  // ── Stat boxes (KpiRow, ProgramStatsRow, BrowseCard metrics) ────────────────
  statBox: {
    background: 'var(--paper)',
    borderRadius: 10,
    padding: '16px 20px',
  },

  // Large KPI number — JetBrains Mono, prominent
  statValue: {
    fontSize: 28,
    fontWeight: 700,
    fontFamily: "'JetBrains Mono', monospace",
    color: 'var(--ink)',
    marginBottom: 4,
    letterSpacing: '-0.02em',
  },

  // Small uppercase label beneath a stat value
  statLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--muted)',
    fontFamily: "'Figtree', sans-serif",
  },

  // ── Pill / occupation tab buttons ───────────────────────────────────────────
  pill: {
    padding: '6px 16px',
    borderRadius: 99,
    border: '1.5px solid var(--rule)',
    background: 'white',
    color: 'var(--ink2)',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: "'Figtree', sans-serif",
    transition: 'all 0.15s',
    whiteSpace: 'nowrap',
  },

  pillActive: {
    padding: '6px 16px',
    borderRadius: 99,
    border: '1.5px solid var(--teal)',
    background: 'var(--teal)',
    color: 'white',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: "'Figtree', sans-serif",
    transition: 'all 0.15s',
    whiteSpace: 'nowrap',
  },

  // ── Table ───────────────────────────────────────────────────────────────────
  tableHeader: {
    padding: '10px 16px',
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.07em',
    textTransform: 'uppercase',
    color: 'var(--muted)',
    fontFamily: "'Figtree', sans-serif",
    background: 'var(--paper)',
    borderBottom: '1.5px solid var(--rule)',
    textAlign: 'left',
  },

  tableCell: {
    padding: '12px 16px',
    fontSize: 14,
    fontFamily: "'Figtree', sans-serif",
    color: 'var(--ink)',
    borderBottom: '1px solid var(--rule)',
  },

  tableRow: {
    background: 'white',
  },

  tableRowAlt: {
    background: 'var(--paper)',
  },
};
