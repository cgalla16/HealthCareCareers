import { S } from '@/lib/styles';

const f$ = n => (n != null ? `$${n.toLocaleString()}` : 'N/A');
const fN = n => (n != null ? n.toLocaleString() : 'N/A');
const fPct = n => (n != null ? `${n.toFixed(0)}%` : 'N/A');

export default function KpiRow({ employment, median, growthPct, numPrograms }) {
  const secondary = [
    { label: 'Total Employed',           value: fN(employment) },
    { label: 'Projected 10-Year Growth', value: fPct(growthPct) },
    { label: 'Accredited Programs',      value: numPrograms > 0 ? numPrograms.toLocaleString() : 'N/A' },
  ];

  return (
    <div style={{ display: 'grid', gap: 12, marginBottom: 32 }}>
      {/* Hero stat */}
      <div
        className="card-hover"
        style={{
          background: 'var(--teal-lt)',
          border: '1.5px solid var(--teal)',
          borderRadius: 12,
          padding: '28px 32px',
        }}
      >
        <div style={{ ...S.statLabel, color: 'var(--teal)', marginBottom: 8 }}>Median Salary</div>
        <div style={{
          fontSize: 48,
          fontWeight: 700,
          fontFamily: "'JetBrains Mono', monospace",
          color: 'var(--ink)',
          letterSpacing: '-0.03em',
          lineHeight: 1,
        }}>
          {f$(median)}
        </div>
        <div style={{ ...S.statLabel, marginTop: 8 }}>National annual median — BLS OEWS May 2024</div>
      </div>

      {/* Secondary stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {secondary.map(({ label, value }) => (
          <div key={label} style={S.statBox}>
            <div style={{ ...S.statValue, fontSize: 24 }}>{value}</div>
            <div style={S.statLabel}>{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
