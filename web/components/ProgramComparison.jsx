'use client';

import { useState } from 'react';
import { S } from '@/lib/styles';
import SiteNav from './SiteNav';

// ── HELPERS ───────────────────────────────────────────────────────────────────
const f$ = n => `$${n.toLocaleString()}`;
const fK = n => `$${(n / 1000).toFixed(0)}k`;

// Keyed by the short abbreviation that getPrograms() stores in p.career
const CAREER_META = {
  PT:  { name: 'Physical Therapists',          degree: 'DPT',       color: 'var(--blue)'  },
  OT:  { name: 'Occupational Therapists',      degree: 'MOT / OTD', color: 'var(--teal)'  },
  RT:  { name: 'Radiation Therapists',         degree: 'BS / AAS',  color: 'var(--amber)' },
  SLP: { name: 'Speech-Language Pathologists', degree: 'MS / PhD',  color: '#7C3AED'      },
};

const METRICS = [
  {
    key: 'cost',   label: 'Total Program Cost',  sub: 'Full program tuition',
    icon: '💰', color: 'var(--amber)', barMax: 250000,
    fmt: p => p.cost != null ? fK(p.cost) : null,
    bar: p => p.cost,
    hi: false, scaffold: true,
  },
  {
    key: 'length', label: 'Program Length',  sub: 'Months to complete',
    icon: '📅', color: 'var(--blue)', barMax: 40,
    fmt: p => p.lengthMonths != null ? `${p.lengthMonths} mo` : null,
    bar: p => p.lengthMonths,
    hi: false, scaffold: true,
  },
  {
    key: 'salary', label: 'Avg Area Salary', sub: 'State BLS annual avg',
    icon: '📍', color: 'var(--teal)', barMax: 130000,
    fmt: p => p.areaSalary != null ? f$(p.areaSalary) : null,
    bar: p => p.areaSalary,
    hi: true, scaffold: false,
  },
  {
    key: 'size',   label: 'Program Size',    sub: 'Students per cohort',
    icon: '👥', color: '#7C3AED', barMax: 200,
    fmt: p => p.programSize != null ? `${p.programSize} students` : null,
    bar: p => p.programSize,
    hi: false, scaffold: false,
  },
  {
    key: 'pass',   label: 'Board Pass Rate', sub: 'First-attempt NBCOT / NPTE',
    icon: '📋', color: 'var(--green)', barMax: 100,
    fmt: p => p.boardPassRate != null ? `${p.boardPassRate.toFixed(1)}%` : null,
    bar: p => p.boardPassRate,
    hi: true, scaffold: false,
  },
];

function winnerOf(programs, metric) {
  if (!programs.length || metric.hi === null || !metric.bar) return null;
  const valid = programs.filter(p => metric.bar(p) != null);
  if (valid.length < 2) return null;
  return valid.reduce((a, b) =>
    metric.hi ? metric.bar(a) >= metric.bar(b) ? a : b
              : metric.bar(a) <= metric.bar(b) ? a : b
  ).id;
}

// ── CAREER CARD ───────────────────────────────────────────────────────────────
function HoverCareerCard({ name, meta, count, onClick }) {
  const [hovered, setHovered] = useState(false);
  const disabled = count === 0;

  return (
    <div
      onClick={() => !disabled && onClick(name)}
      onMouseEnter={() => !disabled && setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'white',
        border: `1.5px solid ${hovered ? meta.color : 'var(--rule)'}`,
        borderRadius: 14,
        padding: '24px 28px',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        position: 'relative',
        transition: 'all 0.18s ease',
        boxShadow: hovered ? '0 8px 24px rgba(0,0,0,0.08)' : 'none',
      }}
    >
      <div style={{ ...S.statLabel, color: meta.color, marginBottom: 8 }}>{name}</div>
      <div style={{ fontSize: 19, fontWeight: 700, fontFamily: "'Fraunces', serif", color: 'var(--ink)', lineHeight: 1.2, marginBottom: 4 }}>
        {meta.name}
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)', fontFamily: "'Figtree', sans-serif", marginBottom: 20 }}>
        {meta.degree}
      </div>
      <div style={{ ...S.statLabel, borderTop: '1px solid var(--rule)', paddingTop: 12 }}>
        {disabled ? 'Coming soon' : `${count} accredited programs`}
      </div>
      <div style={{
        position: 'absolute', right: 22, top: '50%', transform: 'translateY(-50%)',
        fontSize: 18, color: hovered ? meta.color : 'var(--rule)',
        transition: 'color 0.18s',
      }}>→</div>
    </div>
  );
}

// ── BROWSE CARD ───────────────────────────────────────────────────────────────
function BrowseCard({ p, selected, onToggle, disabled }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className={`card-hover ${selected ? 'sel' : ''}`}
      onClick={() => (!disabled || selected) && onToggle(p.id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'white', borderRadius: 14,
        border: `1.5px solid ${selected ? 'var(--teal)' : 'var(--rule)'}`,
        padding: 20, opacity: disabled && !selected ? 0.4 : 1,
        position: 'relative', userSelect: 'none',
      }}
    >
      {selected && (
        <div style={{ position:'absolute',top:12,right:12,width:22,height:22,borderRadius:'50%',background:'var(--teal)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:11,color:'white',fontWeight:900 }}>✓</div>
      )}

      <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:10 }}>
        <span className="pill" style={{ background:'var(--blue-lt)', color:'var(--blue)' }}>
          {p.career} · {p.degreeType}
        </span>
        {p.schoolType && (
          <span className="pill" style={{
            background: p.schoolType === 'public' ? 'var(--teal-lt)' : 'var(--paper)',
            color: p.schoolType === 'public' ? 'var(--teal)' : 'var(--muted)',
          }}>
            {p.schoolType === 'public' ? 'Public' : 'Private'}
          </span>
        )}
      </div>

      <div style={{ fontSize:15,fontWeight:700,color:'var(--ink)',fontFamily:"'Fraunces',serif",lineHeight:1.3,marginBottom:3 }}>
        {p.name}
      </div>
      <div style={{ ...S.statLabel, marginBottom: 14 }}>{p.state}</div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
        {[
          { label:'Pass Rate',   val: p.boardPassRate != null ? `${p.boardPassRate.toFixed(1)}%` : '—',     accent:'var(--green)' },
          { label:'Area Salary', val: p.areaSalary    != null ? fK(p.areaSalary) : '—',                     accent:'var(--teal)'  },
          { label:'Length',      val: p.lengthMonths  != null ? `${p.lengthMonths} mo` : 'Coming soon',      accent:'var(--blue)'  },
          {
            label: p.tuitionIsOos && p.schoolType === 'public' ? 'Total Cost (OOS)' : 'Total Cost',
            val:   p.cost != null ? fK(p.cost) : 'Coming soon',
            accent:'var(--amber)',
          },
        ].map(item => (
          <div key={item.label} style={S.statBox}>
            <div style={{ ...S.statLabel, marginBottom: 2 }}>{item.label}</div>
            <div style={{ fontSize:15,fontWeight:700,color:item.accent,fontFamily:"'JetBrains Mono',monospace" }}>{item.val}</div>
          </div>
        ))}
      </div>

      <div style={{
        ...S.statLabel, marginTop:12, paddingTop:10, borderTop:'1px solid var(--rule)',
        textAlign:'center',
        color: selected ? 'var(--teal)' : hovered && !disabled ? 'var(--ink2)' : 'var(--muted)',
      }}>
        {selected ? '✓ Added to comparison' : hovered && !disabled ? '+ Click to compare' : 'Click to add'}
      </div>
    </div>
  );
}

// ── COMPARE TABLE ─────────────────────────────────────────────────────────────
function CompareTable({ programs, onRemove }) {
  if (!programs.length) return null;
  const N = programs.length;
  const gridCols = `190px repeat(${N}, 1fr)`;
  const winners = Object.fromEntries(METRICS.map(m => [m.key, winnerOf(programs, m)]));

  const HeaderRow = () => (
    <div style={{ display:'grid', gridTemplateColumns:gridCols }}>
      <div style={{ padding:'0 0 14px 0' }} />
      {programs.map((p, i) => (
        <div key={p.id} className={`fade d${Math.min(i+1,4)}`} style={{
          background: 'white',
          borderLeft:  i === 0 ? '1.5px solid var(--rule)' : 'none',
          borderRight: '1.5px solid var(--rule)',
          borderTop:   '1.5px solid var(--rule)',
          borderRadius: i === 0 ? '12px 0 0 0' : i === N-1 ? '0 12px 0 0' : '0',
          padding: '20px 20px 16px',
          position: 'relative',
        }}>
          <button
            onClick={() => onRemove(p.id)}
            style={{ position:'absolute',top:10,right:10,background:'none',border:'none',color:'var(--muted)',cursor:'pointer',fontSize:18,lineHeight:1,padding:'2px 5px',borderRadius:4 }}
            onMouseEnter={e => e.currentTarget.style.color = '#DC2626'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--muted)'}
          >×</button>
          <span className="pill" style={{ background:'var(--blue-lt)', color:'var(--blue)', marginBottom:10 }}>
            {p.career} · {p.degreeType}
          </span>
          <div style={{ fontSize:15,fontWeight:700,color:'var(--ink)',fontFamily:"'Fraunces',serif",lineHeight:1.3,paddingRight:20 }}>{p.name}</div>
          <div style={{ ...S.statLabel, marginTop: 3 }}>{p.state}</div>
        </div>
      ))}
    </div>
  );

  const MetricRows = () => METRICS.map((m, mi) => {
    const rowClass = mi % 2 === 0 ? 'mrow-even' : 'mrow-odd';
    return (
      <div key={m.key} className={`metric-row ${rowClass}`} style={{ display:'grid', gridTemplateColumns:gridCols }}>
        <div style={{ padding:'18px 12px 18px 0',borderBottom:'1px solid var(--rule)',display:'flex',flexDirection:'column',justifyContent:'center' }}>
          <div style={{ display:'flex',alignItems:'center',gap:7,marginBottom:3 }}>
            <span style={{ fontSize:14 }}>{m.icon}</span>
            <span style={{ fontSize:13,fontWeight:700,color:'var(--ink)',fontFamily:"'Figtree',sans-serif" }}>{m.label}</span>
          </div>
          <div style={{ ...S.statLabel, paddingLeft: 21 }}>{m.sub}</div>
        </div>
        {programs.map((p, pi) => {
          const isWinner = winners[m.key] === p.id;
          const isFirst  = pi === 0;
          const val      = m.fmt(p);
          const barVal   = m.bar ? m.bar(p) : null;

          return (
            <div key={p.id} style={{
              padding: '18px 20px',
              borderBottom: '1px solid var(--rule)',
              borderLeft:   isFirst ? '1.5px solid var(--rule)' : 'none',
              borderRight:  '1.5px solid var(--rule)',
              display: 'flex', flexDirection: 'column', justifyContent: 'center',
            }}>
              {val === null ? (
                <span style={{ fontSize:14, color:'var(--muted)', fontFamily:"'Figtree',sans-serif" }}>
                  {m.scaffold ? 'Coming soon' : '—'}
                </span>
              ) : (
                <>
                  <div style={{ display:'flex',alignItems:'baseline',gap:8,justifyContent:'space-between' }}>
                    <span style={{ fontSize:19,fontWeight:700,color:isWinner?m.color:'var(--ink)',fontFamily:"'JetBrains Mono',monospace" }}>
                      {val}
                    </span>
                    {isWinner && (
                      <span className="pill" style={{ background:'var(--teal-lt)',color:'var(--teal)',fontSize:9,padding:'2px 8px' }}>✓ Best</span>
                    )}
                  </div>
                  {barVal != null && m.barMax && (
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width:`${Math.min(100,(barVal/m.barMax)*100)}%`, background:isWinner?m.color:'var(--rule)', opacity:isWinner?1:0.55 }} />
                    </div>
                  )}
                  {m.key === 'cost' && p.tuitionIsOos && p.schoolType === 'public' && (
                    <div style={{ fontSize:10, color:'var(--muted)', fontFamily:"'Figtree',sans-serif", marginTop:3 }}>
                      Out-of-state rate
                      {p.tuitionInstate ? ` · In-state: ${fK(p.tuitionInstate)}/yr` : ''}
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    );
  });

  const CtaRow = () => (
    <div style={{ display:'grid', gridTemplateColumns:gridCols }}>
      <div style={{ padding:'18px 0' }} />
      {programs.map((p, pi) => (
        <div key={p.id} style={{
          padding: '16px 20px',
          borderLeft:   pi === 0 ? '1.5px solid var(--rule)' : 'none',
          borderRight:  '1.5px solid var(--rule)',
          borderBottom: '1.5px solid var(--rule)',
          borderRadius: pi === 0 ? '0 0 0 12px' : pi === N-1 ? '0 0 12px 0' : '0',
          background:   'var(--paper)',
        }}>
          <button className="cta" style={{
            width:'100%', padding:'11px 0', borderRadius:9, border:'none',
            background:'white', color:'var(--ink2)',
            fontSize:13, fontWeight:700, fontFamily:"'Figtree',sans-serif",
            boxShadow:'inset 0 0 0 1.5px var(--rule)',
          }}>
            Request Info →
          </button>
        </div>
      ))}
    </div>
  );

  return (
    <div style={{ overflowX:'auto' }}>
      <div style={{ minWidth: 190 + N * 210 }}>
        <HeaderRow />
        <MetricRows />
        <CtaRow />
      </div>
    </div>
  );
}

// ── INSIGHT STRIP ─────────────────────────────────────────────────────────────
function InsightStrip({ programs }) {
  if (programs.length < 2) return null;

  const withCost      = programs.filter(p => p.cost         != null);
  const withPass      = programs.filter(p => p.boardPassRate != null);
  const withSalary    = programs.filter(p => p.areaSalary   != null);
  const withBothValue = programs.filter(p => p.cost != null && p.boardPassRate != null);

  const cheapest  = withCost.length      ? withCost.reduce((a,b)   => a.cost         <= b.cost         ? a : b) : null;
  const bestPass  = withPass.length      ? withPass.reduce((a,b)   => a.boardPassRate >= b.boardPassRate ? a : b) : null;
  const bestMkt   = withSalary.length    ? withSalary.reduce((a,b) => a.areaSalary   >= b.areaSalary   ? a : b) : null;
  const bestValue = withBothValue.length >= 3
    ? withBothValue.reduce((a, b) => {
        const scoreA = a.boardPassRate / (a.cost / 10000);
        const scoreB = b.boardPassRate / (b.cost / 10000);
        return scoreA >= scoreB ? a : b;
      })
    : null;

  const items = [
    cheapest  && { icon:'💸', label:'Lowest Total Cost',  val:fK(cheapest.cost),                        school:cheapest.name,  accent:'var(--amber)' },
    bestPass  && { icon:'📋', label:'Highest Pass Rate',  val:`${bestPass.boardPassRate.toFixed(1)}%`,  school:bestPass.name,  accent:'var(--green)' },
    bestValue && { icon:'🏆', label:'Best Value',         val:`${bestValue.boardPassRate.toFixed(1)}% · ${fK(bestValue.cost)}`, school:bestValue.name, accent:'#7C3AED' },
    bestMkt   && { icon:'📍', label:'Best Salary Market', val:f$(bestMkt.areaSalary),                   school:bestMkt.name,   accent:'var(--teal)'  },
  ].filter(Boolean);

  if (!items.length) return null;

  return (
    <div style={{ display:'grid', gridTemplateColumns:`repeat(${items.length},1fr)`, border:'1.5px solid var(--rule)', borderRadius:14, overflow:'hidden', marginBottom:24, background:'white' }}>
      {items.map((item, i) => (
        <div key={i} style={{ padding:'20px 24px', borderRight:i < items.length-1 ? '1px solid var(--rule)' : 'none' }}>
          <div style={{ display:'flex',alignItems:'center',gap:7,marginBottom:8 }}>
            <span style={{ fontSize:16 }}>{item.icon}</span>
            <span style={{ ...S.statLabel }}>{item.label}</span>
          </div>
          <div style={{ ...S.statValue, fontSize: 26, color: item.accent, marginBottom: 4 }}>{item.val}</div>
          <div style={{ fontSize:12,color:'var(--muted)',fontFamily:"'Figtree',sans-serif",lineHeight:1.4 }}>{item.school}</div>
        </div>
      ))}
    </div>
  );
}

// ── FILTER BAR ────────────────────────────────────────────────────────────────
function FilterBar({ filters, setFilters, total, careerPrograms, onChangeCareer }) {
  const states = ['All', ...Array.from(new Set(careerPrograms.map(p => p.state))).sort()];

  return (
    <div style={{ display:'flex',flexWrap:'wrap',alignItems:'center',gap:16,padding:'14px 20px',background:'white',border:'1.5px solid var(--rule)',borderRadius:12,marginBottom:20 }}>
      <div style={{ display:'flex',alignItems:'center',gap:7 }}>
        <span style={S.statLabel}>State</span>
        <select
          value={filters.state}
          onChange={e => setFilters(f => ({ ...f, state:e.target.value }))}
          style={{ border:'1.5px solid var(--rule)',borderRadius:99,padding:'5px 12px',fontSize:12,fontFamily:"'Figtree',sans-serif",background:'white',color:'var(--ink2)',cursor:'pointer',outline:'none' }}
        >
          {states.map(s => <option key={s}>{s}</option>)}
        </select>
      </div>

      <div style={{ width:1, height:22, background:'var(--rule)' }} />

      <div style={{ display:'flex',alignItems:'center',gap:7 }}>
        <span style={S.statLabel}>Sort by</span>
        <select
          value={filters.sortBy}
          onChange={e => setFilters(f => ({ ...f, sortBy:e.target.value }))}
          style={{ border:'1.5px solid var(--rule)',borderRadius:99,padding:'5px 12px',fontSize:12,fontFamily:"'Figtree',sans-serif",background:'white',color:'var(--ink2)',cursor:'pointer',outline:'none' }}
        >
          <option value="passRate">Pass Rate</option>
          <option value="salary">Area Salary</option>
          <option value="cost">Lowest Cost</option>
        </select>
      </div>

      <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:16 }}>
        <span style={S.statLabel}>{total} programs</span>
        <button
          onClick={onChangeCareer}
          style={{ fontSize:12,color:'var(--teal)',background:'none',border:'none',cursor:'pointer',fontWeight:700,fontFamily:"'Figtree',sans-serif",textDecoration:'underline' }}
        >
          Change career
        </button>
      </div>
    </div>
  );
}

// ── SELECTION TRAY ────────────────────────────────────────────────────────────
function SelectionTray({ programs, step, onRemove, onCompare }) {
  const visible    = programs.length > 0 && step === 'browse';
  const canCompare = programs.length >= 2;

  return (
    <div style={{
      position: 'fixed', bottom: 24, left: '50%',
      background: 'white', border: '1.5px solid var(--rule)',
      borderRadius: 16, padding: '12px 16px 12px 20px',
      display: 'flex', alignItems: 'center', gap: 14,
      zIndex: 200, boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
      maxWidth: 780, width: 'calc(100vw - 64px)',
      transition: 'opacity 0.25s ease, transform 0.3s cubic-bezier(0.34,1.56,0.64,1)',
      opacity: visible ? 1 : 0,
      transform: `translateX(-50%) translateY(${visible ? 0 : 16}px)`,
      pointerEvents: visible ? 'auto' : 'none',
    }}>
      <span style={{ ...S.statLabel, whiteSpace:'nowrap' }}>Selected:</span>

      <div style={{ display:'flex', gap:6, flex:1, flexWrap:'wrap' }}>
        {programs.map(p => (
          <div key={p.id} style={{
            background: 'var(--paper)', border: '1px solid var(--rule)',
            borderRadius: 20, padding: '4px 8px 4px 12px',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span style={{ fontSize:12, fontFamily:"'Figtree',sans-serif", color:'var(--ink2)' }}>
              {p.name.split(' ').slice(0, 3).join(' ')}
            </span>
            <button
              onClick={() => onRemove(p.id)}
              style={{ cursor:'pointer',fontSize:13,lineHeight:1,padding:'0 2px',border:'none',background:'transparent',color:'var(--muted)' }}
            >×</button>
          </div>
        ))}
      </div>

      <div style={{ display:'flex', gap:5, flexShrink:0 }}>
        {[0,1,2,3].map(i => (
          <div key={i} style={{ width:7, height:7, borderRadius:'50%', background: i < programs.length ? 'var(--teal)' : 'var(--rule)' }} />
        ))}
      </div>

      <button
        onClick={onCompare}
        disabled={!canCompare}
        style={{
          ...S.pillActive,
          borderRadius: 10, padding: '10px 22px', fontSize: 14,
          whiteSpace: 'nowrap', flexShrink: 0,
          ...(canCompare ? {} : { background:'var(--rule)', border:'1.5px solid var(--rule)', color:'var(--muted)', cursor:'not-allowed' }),
        }}
      >
        Compare {programs.length} Program{programs.length !== 1 ? 's' : ''} →
      </button>
    </div>
  );
}

// ── APP ───────────────────────────────────────────────────────────────────────
export default function ProgramComparison({ programs }) {
  const [step, setStep]                     = useState('career');
  const [selectedCareer, setSelectedCareer] = useState(null);
  const [selected, setSelected]             = useState([]);
  const [filters, setFilters]               = useState({ state: 'All', sortBy: 'passRate' });
  const MAX = 4;

  const careerCounts = Object.fromEntries(
    Object.keys(CAREER_META).map(name => [name, programs.filter(p => p.career === name).length])
  );

  const careerPrograms = programs.filter(p => p.career === selectedCareer);

  const filtered = careerPrograms
    .filter(p => filters.state === 'All' || p.state === filters.state)
    .sort((a, b) => {
      if (filters.sortBy === 'salary') return (b.areaSalary ?? 0) - (a.areaSalary ?? 0);
      if (filters.sortBy === 'cost')   return (a.cost ?? Infinity) - (b.cost ?? Infinity);
      return (b.boardPassRate ?? 0) - (a.boardPassRate ?? 0);
    });

  const selectedPrograms = selected.map(id => programs.find(p => p.id === id)).filter(Boolean);

  const toggle = id => setSelected(prev =>
    prev.includes(id) ? prev.filter(x => x !== id)
      : prev.length < MAX ? [...prev, id] : prev
  );

  const goToCareer = () => {
    setSelectedCareer(null);
    setSelected([]);
    setStep('career');
  };

  const selectCareer = name => {
    setSelectedCareer(name);
    setFilters({ state: 'All', sortBy: 'passRate' });
    setStep('browse');
  };

  const careerName = selectedCareer ? CAREER_META[selectedCareer]?.name : null;

  const subtitle =
    step === 'career'  ? 'Choose a career to start comparing accredited programs on cost, pass rates, and salary outcomes.' :
    step === 'browse'  ? `Showing ${filtered.length} ${careerName} programs. Select up to ${MAX} to compare.` :
                         `Comparing ${selectedPrograms.length} programs side by side.`;

  const crumbActive = { fontSize:13, fontWeight:700, color:'var(--ink)',  fontFamily:"'Figtree',sans-serif" };
  const crumbLink   = { fontSize:13, fontWeight:500, color:'var(--teal)', fontFamily:"'Figtree',sans-serif", cursor:'pointer' };
  const crumbDot    = { width:4, height:4, borderRadius:'50%', background:'var(--rule)', flexShrink:0 };

  return (
    <div style={{ minHeight:'100vh', background:'var(--cream)', fontFamily:"'Figtree',sans-serif" }}>
      <SiteNav active="programs" />

      {/* Breadcrumb */}
      <div style={{ background:'white', borderBottom:'1.5px solid var(--rule)', padding:'0 40px', height:40, display:'flex', alignItems:'center', gap:10 }}>
        <span
          onClick={step !== 'career' ? goToCareer : undefined}
          style={step === 'career' ? crumbActive : crumbLink}
        >
          Choose Career
        </span>
        {step !== 'career' && (
          <>
            <div style={crumbDot} />
            <span
              onClick={step === 'compare' ? () => setStep('browse') : undefined}
              style={step === 'browse' ? crumbActive : crumbLink}
            >
              Browse {careerName}
            </span>
          </>
        )}
        {step === 'compare' && (
          <>
            <div style={crumbDot} />
            <span style={crumbActive}>Compare {selectedPrograms.length} Programs</span>
          </>
        )}
      </div>

      {/* Hero */}
      <div style={{ padding:'40px 40px 32px', background:'white', borderBottom:'1.5px solid var(--rule)' }}>
        <div style={{ maxWidth:1280, margin:'0 auto', display:'flex', alignItems:'flex-end', gap:16, flexWrap:'wrap', justifyContent:'space-between' }}>
          <div>
            <div style={{ ...S.statLabel, color:'var(--teal)', marginBottom:10 }}>◆ Program Intelligence</div>
            <h1 style={{ fontSize:38, fontWeight:900, fontFamily:"'Fraunces',serif", color:'var(--ink)', letterSpacing:'-0.02em', lineHeight:1.1 }}>
              Compare Programs<br/><span style={{ color:'var(--teal)' }}>Side by Side</span>
            </h1>
            <p style={{ marginTop:12, fontSize:14, color:'var(--muted)', maxWidth:520, lineHeight:1.7 }}>
              {subtitle}
            </p>
          </div>
          {step === 'browse' && selected.length >= 2 && (
            <button className="cta" onClick={() => setStep('compare')} style={{ padding:'12px 28px',borderRadius:10,border:'none',background:'var(--teal)',color:'white',fontSize:14,fontWeight:700,cursor:'pointer',fontFamily:"'Figtree',sans-serif" }}>
              Compare {selected.length} Programs →
            </button>
          )}
        </div>
      </div>

      {/* Main */}
      <main style={{ ...S.pageWrapper }}>

        {/* STEP: CAREER */}
        {step === 'career' && (
          <div className="fade" style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(240px,1fr))', gap:16 }}>
            {Object.entries(CAREER_META).map(([name, meta]) => (
              <HoverCareerCard
                key={name}
                name={name}
                meta={meta}
                count={careerCounts[name]}
                onClick={selectCareer}
              />
            ))}
          </div>
        )}

        {/* STEP: BROWSE */}
        {step === 'browse' && (
          <div className="fade">
            <FilterBar
              filters={filters}
              setFilters={setFilters}
              total={filtered.length}
              careerPrograms={careerPrograms}
              onChangeCareer={goToCareer}
            />
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(210px,1fr))', gap:14 }}>
              {filtered.map((p, i) => (
                <div key={p.id} className={`fade d${Math.min(i+1,4)}`}>
                  <BrowseCard
                    p={p}
                    selected={selected.includes(p.id)}
                    onToggle={toggle}
                    disabled={selected.length >= MAX && !selected.includes(p.id)}
                  />
                </div>
              ))}
              {filtered.length === 0 && (
                <div style={{ gridColumn:'1/-1', textAlign:'center', padding:'60px 0', color:'var(--muted)' }}>
                  No programs match your filters.
                </div>
              )}
            </div>
          </div>
        )}

        {/* STEP: COMPARE */}
        {step === 'compare' && (
          <div className="fade">
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:20 }}>
              <button
                onClick={() => setStep('browse')}
                style={{ fontSize:13,color:'var(--teal)',background:'none',border:'none',cursor:'pointer',fontWeight:700,fontFamily:"'Figtree',sans-serif" }}
              >
                ← Back to browse
              </button>
              <button
                onClick={() => setSelected([])}
                style={{ fontSize:12,color:'var(--muted)',background:'none',border:'none',cursor:'pointer',fontFamily:"'Figtree',sans-serif",textDecoration:'underline' }}
              >
                Clear all
              </button>
            </div>
            {selectedPrograms.length === 0 ? (
              <div style={{ textAlign:'center', padding:'80px 20px', border:'1.5px dashed var(--rule)', borderRadius:16 }}>
                <div style={{ fontSize:40, marginBottom:16 }}>📊</div>
                <div style={{ fontSize:20, fontWeight:700, color:'var(--ink)', fontFamily:"'Fraunces',serif", marginBottom:8 }}>No programs selected yet</div>
                <p style={{ fontSize:14, color:'var(--muted)', marginBottom:24 }}>Head to Browse and pick up to 4 programs to compare.</p>
                <button className="cta" onClick={() => setStep('browse')} style={{ padding:'11px 28px',borderRadius:10,border:'none',background:'var(--teal)',color:'white',fontSize:14,fontWeight:700,cursor:'pointer',fontFamily:"'Figtree',sans-serif" }}>
                  Browse Programs →
                </button>
              </div>
            ) : (
              <>
                <InsightStrip programs={selectedPrograms} />
                <CompareTable programs={selectedPrograms} onRemove={toggle} />
              </>
            )}
          </div>
        )}
      </main>

      <SelectionTray
        programs={selectedPrograms}
        step={step}
        onRemove={toggle}
        onCompare={() => setStep('compare')}
      />
    </div>
  );
}
