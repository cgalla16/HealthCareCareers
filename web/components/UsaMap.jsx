'use client';

import { useState } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import { scaleSequential } from 'd3-scale';
import { interpolateRgb } from 'd3-interpolate';

const interpolateBlues = interpolateRgb('#DBEAFE', '#1E3A8A');

import OccupationNav from './OccupationNav';
import { S } from '@/lib/styles';
import { OCCUPATIONS } from '@/lib/constants';

const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json';

const f$ = n => `$${Math.round(n).toLocaleString()}`;
const fN = n => n.toLocaleString();

/**
 * allData — object keyed by occupation slug, each value is an array of:
 *   { stateName, stateAbbrev, annualMeanWage, annualMedianWage, employees }
 */
export default function UsaMap({ allData }) {
  const [activeSlug, setActiveSlug]   = useState('physical-therapists');
  const [tooltip, setTooltip]         = useState(null); // { x, y, state }

  const data     = allData[activeSlug] ?? [];
  const byAbbrev = Object.fromEntries(
    data.filter(d => d.stateAbbrev).map(d => [d.stateAbbrev, d])
  );

  const wages     = data.map(d => d.annualMeanWage).filter(Boolean);
  const minWage   = wages.length ? Math.min(...wages) : 60000;
  const maxWage   = wages.length ? Math.max(...wages) : 130000;
  const colorScale = scaleSequential(interpolateBlues).domain([minWage * 0.9, maxWage]);

  const missingStates = data
    .filter(d => d.annualMeanWage == null && d.stateName !== 'Puerto Rico')
    .map(d => d.stateName)
    .sort();

  // Puerto Rico — show as text note since it's not in the standard TopoJSON
  const prData = byAbbrev['PR'];

  const slugToName = Object.fromEntries(OCCUPATIONS.map(o => [o.slug, o.name]));
  const occupationName = slugToName[activeSlug] ?? 'Healthcare Workers';

  return (
    <div style={{ background: 'var(--cream)', padding: '32px 40px 48px' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>

        {/* Section header */}
        <h2 style={{ ...S.sectionHeading, marginBottom: 4 }}>
          Where {occupationName} Earn the Most
        </h2>
        <p style={{ fontSize: 13, fontWeight: 400, color: 'var(--muted)', marginBottom: 24, fontFamily: "'Figtree', sans-serif" }}>
          Average annual salaries by state — BLS OEWS May 2024
        </p>

        {/* Occupation selector */}
        <div style={{ marginBottom: 20 }}>
          <OccupationNav activeSlug={activeSlug} onChange={setActiveSlug} />
        </div>

        {/* Map card */}
        <div style={{ background: 'white', border: '1.5px solid var(--rule)', borderRadius: 16, padding: '20px 24px', position: 'relative' }}>
          <ComposableMap
            projection="geoAlbersUsa"
            style={{ width: '100%', height: 'auto' }}
          >
            <Geographies geography={GEO_URL}>
              {({ geographies }) =>
                geographies.map(geo => {
                  const abbrev  = geo.properties.name
                    ? stateNameToAbbrev(geo.properties.name)
                    : null;
                  const stateData = abbrev ? byAbbrev[abbrev] : null;
                  const fill = stateData?.annualMeanWage
                    ? colorScale(stateData.annualMeanWage)
                    : 'var(--rule)';

                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      fill={fill}
                      stroke="white"
                      strokeWidth={0.5}
                      style={{
                        default: { outline: 'none' },
                        hover:   { outline: 'none', opacity: 0.85, cursor: 'pointer' },
                        pressed: { outline: 'none' },
                      }}
                      onMouseMove={e => {
                        if (!stateData) return;
                        setTooltip({ x: e.clientX, y: e.clientY, state: stateData });
                      }}
                      onMouseLeave={() => setTooltip(null)}
                    />
                  );
                })
              }
            </Geographies>
          </ComposableMap>

          {/* Hover tooltip */}
          {tooltip && (
            <div style={{
              position: 'fixed',
              left: tooltip.x + 14,
              top:  tooltip.y - 10,
              background: 'var(--ink)',
              color: 'white',
              borderRadius: 8,
              padding: '10px 14px',
              fontSize: 13,
              fontFamily: "'Figtree', sans-serif",
              pointerEvents: 'none',
              zIndex: 999,
              boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
              minWidth: 180,
            }}>
              <div style={{ fontWeight: 700, marginBottom: 6, fontSize: 14 }}>
                {tooltip.state.stateName}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 2 }}>
                <span style={{ color: '#9CA3AF' }}>Mean wage</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}>
                  {tooltip.state.annualMeanWage ? f$(tooltip.state.annualMeanWage) : '—'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 2 }}>
                <span style={{ color: '#9CA3AF' }}>Median wage</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}>
                  {tooltip.state.annualMedianWage ? f$(tooltip.state.annualMedianWage) : '—'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
                <span style={{ color: '#9CA3AF' }}>Employed</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}>
                  {tooltip.state.employees ? fN(tooltip.state.employees) : '—'}
                </span>
              </div>
            </div>
          )}

          {/* Color legend — inside card */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, justifyContent: 'flex-end' }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', fontFamily: "'Figtree', sans-serif" }}>{f$(minWage)}</span>
            <div style={{
              width: 160, height: 10, borderRadius: 5,
              background: `linear-gradient(to right, ${interpolateBlues(0.2)}, ${interpolateBlues(1)})`,
            }} />
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', fontFamily: "'Figtree', sans-serif" }}>{f$(maxWage)}</span>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', fontFamily: "'Figtree', sans-serif", marginLeft: 8 }}>Annual Mean Wage</span>
          </div>
        </div>

        {/* Puerto Rico note */}
        {prData?.annualMeanWage && (
          <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', fontFamily: "'Figtree', sans-serif", margin: '12px 0 0' }}>
            Puerto Rico (not shown on map) — Mean: {f$(prData.annualMeanWage)}
            {prData.annualMedianWage ? ` · Median: ${f$(prData.annualMedianWage)}` : ''}
          </p>
        )}

        {/* Missing states note */}
        {missingStates.length > 0 && (
          <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', fontFamily: "'Figtree', sans-serif", margin: '6px 0 0' }}>
            No data available: {missingStates.join(', ')}
          </p>
        )}
      </div>
    </div>
  );
}

// react-simple-maps us-atlas uses full state names in properties.name
// Build a reverse lookup from the STATE_ABBREVS we already have
const NAME_TO_ABBREV = {
  Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA',
  Colorado: 'CO', Connecticut: 'CT', Delaware: 'DE', Florida: 'FL', Georgia: 'GA',
  Hawaii: 'HI', Idaho: 'ID', Illinois: 'IL', Indiana: 'IN', Iowa: 'IA',
  Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA', Maine: 'ME', Maryland: 'MD',
  Massachusetts: 'MA', Michigan: 'MI', Minnesota: 'MN', Mississippi: 'MS',
  Missouri: 'MO', Montana: 'MT', Nebraska: 'NE', Nevada: 'NV',
  'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
  'North Carolina': 'NC', 'North Dakota': 'ND', Ohio: 'OH', Oklahoma: 'OK',
  Oregon: 'OR', Pennsylvania: 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
  'South Dakota': 'SD', Tennessee: 'TN', Texas: 'TX', Utah: 'UT', Vermont: 'VT',
  Virginia: 'VA', Washington: 'WA', 'West Virginia': 'WV', Wisconsin: 'WI',
  Wyoming: 'WY', 'District of Columbia': 'DC',
};

function stateNameToAbbrev(name) {
  return NAME_TO_ABBREV[name] ?? null;
}
