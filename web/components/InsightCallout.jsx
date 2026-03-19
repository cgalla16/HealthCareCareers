import { S } from '@/lib/styles';

const f$ = n => (n != null ? `$${Math.round(n).toLocaleString()}` : '—');

/**
 * Server component — displays a highlighted insight callout.
 * Props:
 *   settingName  — e.g. "Home Health Care Services"
 *   medianWage   — number (annual)
 *   meanWage     — number (annual)
 */
export default function InsightCallout({ settingName, medianWage, meanWage }) {
  if (!settingName) return null;

  return (
    <div style={{
      background: 'var(--blue-lt)',
      border: '1.5px solid var(--blue)',
      borderRadius: 12,
      padding: '20px 18px',
      height: 'fit-content',
    }}>
      <div style={{ ...S.statLabel, color: 'var(--blue)', marginBottom: 12 }}>
        Top Work Setting
      </div>
      <div style={{
        fontSize: 16,
        fontWeight: 700,
        fontFamily: "'Fraunces', serif",
        color: 'var(--ink)',
        marginBottom: 12,
        lineHeight: 1.3,
      }}>
        {settingName}
      </div>
      <div style={{ display: 'flex', gap: 16, marginBottom: 14 }}>
        {medianWage != null && (
          <div>
            <div style={{ ...S.statValue, fontSize: 20 }}>{f$(medianWage)}</div>
            <div style={S.statLabel}>Median</div>
          </div>
        )}
        {meanWage != null && (
          <div>
            <div style={{ ...S.statValue, fontSize: 20 }}>{f$(meanWage)}</div>
            <div style={S.statLabel}>Mean</div>
          </div>
        )}
      </div>
      <p style={{ fontSize: 12, color: 'var(--ink2)', lineHeight: 1.5, margin: 0, fontFamily: "'Figtree', sans-serif" }}>
        {settingName} offers the highest median salaries among tracked work settings for this occupation.
      </p>
    </div>
  );
}
