import { S } from '@/lib/styles';

const f$ = n => (n != null ? `$${Math.round(n).toLocaleString()}` : '—');
const fPct = n => (n != null ? `${n.toFixed(1)}%` : '—');

export default function WorkSettingsTable({ rows }) {
  if (!rows || rows.length === 0) return null;

  return (
    <div style={{ border: '1.5px solid var(--rule)', borderRadius: 12, overflow: 'hidden', marginBottom: 32 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {['Work Setting', '% of Employment', 'Mean Salary', 'Median Salary'].map(h => (
              <th key={h} style={S.tableHeader}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.settingName} style={i % 2 === 0 ? S.tableRow : S.tableRowAlt}>
              <td style={{ ...S.tableCell, fontWeight: 600 }}>{row.settingName}</td>
              <td style={{ ...S.tableCell, fontFamily: "'JetBrains Mono', monospace" }}>{fPct(row.pctOfTotal)}</td>
              <td style={{ ...S.tableCell, fontFamily: "'JetBrains Mono', monospace" }}>{f$(row.meanWage)}</td>
              <td style={{ ...S.tableCell, fontFamily: "'JetBrains Mono', monospace" }}>{f$(row.medianWage)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
