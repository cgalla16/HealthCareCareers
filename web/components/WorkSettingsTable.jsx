'use client';

import { useState } from 'react';
import { S } from '@/lib/styles';

const f$ = n => (n != null ? `$${Math.round(n).toLocaleString()}` : '—');
const fPct = n => (n != null ? `${n.toFixed(1)}%` : '—');

export default function WorkSettingsTable({ rows }) {
  const [hoveredRow, setHoveredRow] = useState(null);

  if (!rows || rows.length === 0) return null;

  const maxMean = Math.max(...rows.map(r => r.meanWage ?? 0));

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
          {rows.map((row, i) => {
            const isTop     = row.meanWage === maxMean;
            const isHovered = hoveredRow === i;
            const bg = isTop
              ? 'var(--blue-lt)'
              : isHovered
                ? 'var(--paper)'
                : i % 2 === 0 ? 'white' : 'var(--paper)';

            return (
              <tr
                key={row.settingName}
                onMouseEnter={() => setHoveredRow(i)}
                onMouseLeave={() => setHoveredRow(null)}
                style={{ background: bg, transition: 'background 0.12s' }}
              >
                <td style={{ ...S.tableCell, fontWeight: isTop ? 700 : 600 }}>
                  {row.settingName}
                  {isTop && (
                    <span style={{
                      marginLeft: 8,
                      fontSize: 10,
                      fontWeight: 700,
                      letterSpacing: '0.07em',
                      textTransform: 'uppercase',
                      color: 'var(--blue)',
                      background: 'var(--blue-lt)',
                      padding: '2px 6px',
                      borderRadius: 4,
                      fontFamily: "'Figtree', sans-serif",
                    }}>
                      Highest
                    </span>
                  )}
                </td>
                <td style={{ ...S.tableCell, fontFamily: "'JetBrains Mono', monospace" }}>
                  {fPct(row.pctOfTotal)}
                </td>
                <td style={S.tableCell}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", minWidth: 80 }}>
                      {f$(row.meanWage)}
                    </span>
                    <div style={{ flex: 1, height: 4, background: 'var(--rule)', borderRadius: 2 }}>
                      <div style={{
                        width: `${maxMean > 0 ? (row.meanWage / maxMean) * 100 : 0}%`,
                        height: 4,
                        background: isTop ? 'var(--blue)' : 'var(--teal)',
                        borderRadius: 2,
                        transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
                      }} />
                    </div>
                  </div>
                </td>
                <td style={{ ...S.tableCell, fontFamily: "'JetBrains Mono', monospace" }}>
                  {f$(row.medianWage)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
