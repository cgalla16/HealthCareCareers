import { S } from '@/lib/styles';

const fN = n => (n != null ? n.toLocaleString() : 'N/A');

export default function ProgramStatsRow({ totalGraduates, avgSize, numPrograms }) {
  const stats = [
    { label: 'Graduates Tested Annually', value: fN(totalGraduates) },
    { label: 'Avg Program Size',          value: fN(avgSize) },
    { label: 'Programs Available',        value: numPrograms > 0 ? numPrograms.toLocaleString() : 'N/A' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 32 }}>
      {stats.map(({ label, value }) => (
        <div key={label} style={S.statBox}>
          <div style={S.statValue}>{value}</div>
          <div style={S.statLabel}>{label}</div>
        </div>
      ))}
    </div>
  );
}
