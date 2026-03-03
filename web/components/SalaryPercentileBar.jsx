'use client';

import { useRef, useState, useEffect } from 'react';

const fK = n => `$${Math.round(n / 1000)}k`;
const PERCENTILES = [
  { key: 'p10',    label: '10th' },
  { key: 'p25',    label: '25th' },
  { key: 'median', label: 'Median' },
  { key: 'p75',    label: '75th' },
  { key: 'p90',    label: '90th' },
];

export default function SalaryPercentileBar({ p10, p25, median, p75, p90 }) {
  const containerRef = useRef(null);
  const [svgWidth, setSvgWidth] = useState(600);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      setSvgWidth(entries[0].contentRect.width);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const vals = { p10, p25, median, p75, p90 };
  if (Object.values(vals).some(v => v == null)) return null;

  const PAD   = 40;
  const range = p90 - p10;
  const x     = val => PAD + ((val - p10) / range) * (svgWidth - PAD * 2);

  const barTop    = 36;
  const barHeight = 20;
  const barMid    = barTop + barHeight / 2;

  const svgHeight = 90;

  return (
    <div ref={containerRef} style={{ marginBottom: 32 }}>
      <svg width="100%" height={svgHeight} style={{ overflow: 'visible', display: 'block' }}>
        {/* Outer band: p10 → p90 */}
        <rect
          x={x(p10)} y={barTop}
          width={x(p90) - x(p10)} height={barHeight}
          rx={barHeight / 2} fill="#BFDBFE"
        />

        {/* IQR band: p25 → p75 */}
        <rect
          x={x(p25)} y={barTop}
          width={x(p75) - x(p25)} height={barHeight}
          rx={barHeight / 2} fill="#3B82F6"
        />

        {/* Median line */}
        <rect
          x={x(median) - 1.5} y={barTop - 4}
          width={3} height={barHeight + 8}
          rx={2} fill="white"
        />

        {/* Dots + labels */}
        {PERCENTILES.map(({ key, label }) => {
          const cx       = x(vals[key]);
          const isMedian = key === 'median';
          return (
            <g key={key}>
              {/* Dollar label above */}
              <text
                x={cx} y={barTop - 10}
                textAnchor="middle"
                style={{
                  fontSize: 12,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontWeight: isMedian ? 700 : 500,
                  fill: isMedian ? '#1D4ED8' : '#44403C',
                }}
              >
                {fK(vals[key])}
              </text>

              {/* Dot */}
              <circle cx={cx} cy={barMid} r={4} fill="white" />

              {/* Percentile label below */}
              <text
                x={cx} y={barTop + barHeight + 18}
                textAnchor="middle"
                style={{
                  fontSize: 10,
                  fontFamily: "'Figtree', sans-serif",
                  fontWeight: isMedian ? 700 : 400,
                  fill: isMedian ? '#1D4ED8' : '#9B9890',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
