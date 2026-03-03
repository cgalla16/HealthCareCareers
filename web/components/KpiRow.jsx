import { S } from '@/lib/styles';

const f$ = n => (n != null ? `$${n.toLocaleString()}` : 'N/A');
const fN = n => (n != null ? n.toLocaleString() : 'N/A');
const fPct = n => (n != null ? `${n.toFixed(0)}%` : 'N/A');

export default function KpiRow({ employment, median, growthPct, numPrograms }) {
  const stats = [
    { label: 'Total Employed',          value: fN(employment) },
    { label: 'Median Salary',           value: f$(median) },
    { label: 'Projected 10-Year Growth',value: fPct(growthPct) },
    { label: 'Accredited Programs',     value: numPrograms > 0 ? numPrograms.toLocaleString() : 'N/A' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 32 }}>
      {stats.map(({ label, value }) => (
        <div key={label} style={S.statBox}>
          <div style={S.statValue}>{value}</div>
          <div style={S.statLabel}>{label}</div>
        </div>
      ))}
    </div>
  );
}
