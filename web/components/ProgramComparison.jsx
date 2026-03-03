'use client';

import { useState } from 'react';
import { S } from '@/lib/styles';
import SiteNav from './SiteNav';

// ── HELPERS ───────────────────────────────────────────────────────────────────
const f$ = n => `$${n.toLocaleString()}`;
const fK = n => `$${(n / 1000).toFixed(0)}k`;

// Returns null when data is missing so cells can show "—" or "Coming soon"
const METRICS = [
  {
    key: 'cost',   label: 'Program Cost',    sub: 'Total tuition',
    icon: '💰', color: 'var(--amber)', barMax: 90000,
    fmt: p => p.cost != null ? f$(p.cost) : null,
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

// Requires 2+ programs with non-null values to crown a winner
function winnerOf(programs, metric) {
  if (!programs.length || metric.hi === null || !metric.bar) return null;
  const valid = programs.filter(p => metric.bar(p) != null);
  if (valid.length < 2) return null;
  return valid.reduce((a, b) =>
    metric.hi ? metric.bar(a) >= metric.bar(b) ? a : b
              : metric.bar(a) <= metric.bar(b) ? a : b
  ).id;
}

// ── BROWSE CARD ───────────────────────────────────────────────────────────────
function BrowseCard({ p, selected, onToggle, disabled }) {
  return (
    <div
      className={`card-hover ${selected ? 'sel' : ''}`}
      onClick={() => (!disabled || selected) && onToggle(p.id)}
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

      <span className="pill" style={{ background:'var(--blue-lt)', color:'var(--blue)', marginBottom:10 }}>
        {p.career} · {p.degreeType}
      </span>

      <div style={{ fontSize:15,fontWeight:700,color:'var(--ink)',fontFamily:"'Fraunces',serif",lineHeight:1.3,marginBottom:3 }}>
        {p.name}
      </div>
      <div style={{ ...S.statLabel, marginBottom: 14 }}>{p.state}</div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
        {[
          { label:'Pass Rate',   val: p.boardPassRate != null ? `${p.boardPassRate.toFixed(1)}%` : '—',       accent:'var(--green)' },
          { label:'Area Salary', val: p.areaSalary    != null ? fK(p.areaSalary) : '—',                       accent:'var(--teal)'  },
          { label:'Length',      val: p.lengthMonths  != null ? `${p.lengthMonths} mo` : 'Coming soon',        accent:'var(--blue)'  },
          { label:'Cost',        val: p.cost          != null ? fK(p.cost) : 'Coming soon',                    accent:'var(--amber)' },
        ].map(item => (
          <div key={item.label} style={S.statBox}>
            <div style={{ ...S.statLabel, marginBottom: 2 }}>{item.label}</div>
            <div style={{ fontSize:15,fontWeight:700,color:item.accent,fontFamily:"'JetBrains Mono',monospace" }}>{item.val}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── COMPARISON TABLE ──────────────────────────────────────────────────────────
function CompareTable({ programs, onRemove }) {
  if (!programs.length) return null;
  const N = programs.length;
  const gridCols = `190px repeat(${N}, 1fr)`;
  const winners = Object.fromEntries(METRICS.map(m => [m.key, winnerOf(programs, m)]));

  const HeaderRow = () => (
    <div style={{ display:'grid', gridTemplateColumns:gridCols, gap:0 }}>
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
        {/* Label */}
        <div style={{ padding:'18px 12px 18px 0',borderBottom:'1px solid var(--rule)',display:'flex',flexDirection:'column',justifyContent:'center' }}>
          <div style={{ display:'flex',alignItems:'center',gap:7,marginBottom:3 }}>
            <span style={{ fontSize:14 }}>{m.icon}</span>
            <span style={{ fontSize:13,fontWeight:700,color:'var(--ink)',fontFamily:"'Figtree',sans-serif" }}>{m.label}</span>
          </div>
          <div style={{ ...S.statLabel, paddingLeft: 21 }}>{m.sub}</div>
        </div>

        {/* Data cells */}
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

  const withCost   = programs.filter(p => p.cost         != null);
  const withPass   = programs.filter(p => p.boardPassRate != null);
  const withSalary = programs.filter(p => p.areaSalary   != null);

  const cheapest = withCost.length   ? withCost.reduce((a,b)   => a.cost         <= b.cost         ? a : b) : null;
  const bestPass = withPass.length   ? withPass.reduce((a,b)   => a.boardPassRate >= b.boardPassRate ? a : b) : null;
  const bestMkt  = withSalary.length ? withSalary.reduce((a,b) => a.areaSalary   >= b.areaSalary   ? a : b) : null;

  const items = [
    cheapest && { icon:'💸', label:'Lowest Tuition',     val:f$(cheapest.cost),              school:cheapest.name, accent:'var(--amber)' },
    bestPass && { icon:'📋', label:'Highest Pass Rate',  val:`${bestPass.boardPassRate.toFixed(1)}%`, school:bestPass.name, accent:'var(--green)' },
    bestMkt  && { icon:'📍', label:'Best Salary Market', val:f$(bestMkt.areaSalary),          school:bestMkt.name,  accent:'var(--teal)'  },
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
function FilterBar({ filters, setFilters, total, allPrograms }) {
  const careers = ['All', ...Array.from(new Set(allPrograms.map(p => p.career))).sort()];
  const states  = ['All', ...Array.from(new Set(allPrograms.map(p => p.state))).sort()];

  return (
    <div style={{ display:'flex',flexWrap:'wrap',alignItems:'center',gap:16,padding:'14px 20px',background:'white',border:'1.5px solid var(--rule)',borderRadius:12,marginBottom:20 }}>
      <div style={{ display:'flex',alignItems:'center',gap:7 }}>
        <span style={S.statLabel}>Career</span>
        <div style={{ display:'flex',gap:5 }}>
          {careers.map(v => (
            <button
              key={v}
              onClick={() => setFilters(f => ({ ...f, career:v }))}
              style={filters.career === v ? { ...S.pillActive, fontSize: 12, padding: '5px 14px' } : { ...S.pill, fontSize: 12, padding: '5px 14px' }}
            >
              {v}
            </button>
          ))}
        </div>
      </div>
      <div style={{ width:1,height:22,background:'var(--rule)' }} />
      <div style={{ display:'flex',alignItems:'center',gap:7 }}>
        <span style={S.statLabel}>State</span>
        <select
          value={filters.state}
          onChange={e => setFilters(f => ({ ...f, state:e.target.value }))}
          style={{ border:'1.5px solid var(--rule)',borderRadius:99,padding:'5px 12px',fontSize:12,fontFamily:"'Figtree',sans-serif",background:'white',color:'var(--ink2)',cursor:'pointer' }}
        >
          {states.map(s => <option key={s}>{s}</option>)}
        </select>
      </div>
      <div style={{ marginLeft:'auto', ...S.statLabel }}>{total} programs</div>
    </div>
  );
}

// ── APP ───────────────────────────────────────────────────────────────────────
export default function ProgramComparison({ programs }) {
  const [selected, setSelected] = useState([]);
  const [view, setView]         = useState('browse');
  const [filters, setFilters]   = useState({ career:'All', state:'All' });
  const MAX = 4;

  const filtered = programs.filter(p =>
    (filters.career === 'All' || p.career === filters.career) &&
    (filters.state  === 'All' || p.state  === filters.state)
  );

  const selectedPrograms = selected.map(id => programs.find(p => p.id === id)).filter(Boolean);

  const toggle = id => setSelected(prev =>
    prev.includes(id) ? prev.filter(x => x !== id)
      : prev.length < MAX ? [...prev, id] : prev
  );

  return (
    <div style={{ minHeight:'100vh', background:'var(--cream)', fontFamily:"'Figtree',sans-serif" }}>
      <SiteNav active="programs" />

      {/* Browse/Compare toggle row */}
      <div style={{ background:'white', borderBottom:'1.5px solid var(--rule)', padding:'0 40px', height:48, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div style={{ display:'flex',background:'var(--paper)',borderRadius:9,padding:3,border:'1.5px solid var(--rule)',gap:2 }}>
          {[{id:'browse',label:'Browse'},{id:'compare',label:'Compare'}].map(v => (
            <button key={v.id} onClick={() => setView(v.id)} style={{
              padding:'6px 18px', borderRadius:7, border:'none',
              background: view === v.id ? 'white' : 'transparent',
              color: view === v.id ? 'var(--teal)' : 'var(--muted)',
              fontWeight: view === v.id ? 700 : 500,
              fontSize:13, cursor:'pointer',
              fontFamily:"'Figtree',sans-serif",
              boxShadow: view === v.id ? '0 1px 4px rgba(28,25,23,0.08)' : 'none',
              transition:'all 0.15s',
            }}>{v.label}</button>
          ))}
        </div>

        <div style={{ ...S.statLabel }}>
          <span style={{ color:selected.length >= MAX ? '#DC2626' : 'var(--teal)', fontWeight:700 }}>{selected.length}</span>/{MAX} selected
        </div>
      </div>

      {/* HEADER */}
      <div style={{ padding:'40px 40px 32px',background:'white',borderBottom:'1.5px solid var(--rule)' }}>
        <div style={{ maxWidth:1280,margin:'0 auto' }}>
          <div style={{ display:'flex',alignItems:'flex-end',gap:16,flexWrap:'wrap',justifyContent:'space-between' }}>
            <div>
              <div style={{ fontSize:11,fontWeight:700,letterSpacing:'0.12em',textTransform:'uppercase',color:'var(--teal)',marginBottom:10,fontFamily:"'Figtree',sans-serif" }}>◆ Program Intelligence</div>
              <h1 style={{ fontSize:38,fontWeight:900,fontFamily:"'Fraunces',serif",color:'var(--ink)',letterSpacing:'-0.02em',lineHeight:1.1 }}>
                Compare Programs<br/><span style={{ color:'var(--teal)' }}>Side by Side</span>
              </h1>
              <p style={{ marginTop:12,fontSize:14,color:'var(--muted)',maxWidth:520,lineHeight:1.7,fontFamily:"'Figtree',sans-serif" }}>
                Outcomes, salary potential, and program fit — all in one place. Pick up to 4 programs in Browse, then compare.
              </p>
            </div>
            {view === 'browse' && selected.length > 0 && (
              <button className="cta" onClick={() => setView('compare')} style={{ padding:'12px 28px',borderRadius:10,border:'none',background:'var(--teal)',color:'white',fontSize:14,fontWeight:700,cursor:'pointer',fontFamily:"'Figtree',sans-serif" }}>
                Compare {selected.length} Program{selected.length > 1 ? 's' : ''} →
              </button>
            )}
          </div>
        </div>
      </div>

      {/* MAIN */}
      <main style={{ maxWidth:1280,margin:'0 auto',padding:'32px 40px 80px' }}>
        <FilterBar filters={filters} setFilters={setFilters} total={filtered.length} allPrograms={programs} />

        {/* BROWSE */}
        {view === 'browse' && (
          <div className="fade" style={{ display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(210px,1fr))',gap:14 }}>
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
              <div style={{ gridColumn:'1/-1',textAlign:'center',padding:'60px 0',color:'var(--muted)',fontFamily:"'Figtree',sans-serif" }}>No programs match your filters.</div>
            )}
          </div>
        )}

        {/* COMPARE */}
        {view === 'compare' && (
          <div className="fade">
            {selectedPrograms.length === 0 ? (
              <div style={{ textAlign:'center',padding:'80px 20px',border:'1.5px dashed var(--rule)',borderRadius:16 }}>
                <div style={{ fontSize:40,marginBottom:16 }}>📊</div>
                <div style={{ fontSize:20,fontWeight:700,color:'var(--ink)',fontFamily:"'Fraunces',serif",marginBottom:8 }}>No programs selected yet</div>
                <p style={{ fontSize:14,color:'var(--muted)',marginBottom:24,fontFamily:"'Figtree',sans-serif" }}>Head to Browse and pick up to 4 programs to compare.</p>
                <button className="cta" onClick={() => setView('browse')} style={{ padding:'11px 28px',borderRadius:10,border:'none',background:'var(--teal)',color:'white',fontSize:14,fontWeight:700,cursor:'pointer',fontFamily:"'Figtree',sans-serif" }}>Browse Programs →</button>
              </div>
            ) : (
              <>
                <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:20 }}>
                  <div style={{ fontSize:13,color:'var(--muted)',fontFamily:"'Figtree',sans-serif" }}>
                    Comparing <strong style={{ color:'var(--ink)' }}>{selectedPrograms.length}</strong> program{selectedPrograms.length > 1 ? 's' : ''}
                    {selectedPrograms.length < MAX && (
                      <button onClick={() => setView('browse')} style={{ marginLeft:12,fontSize:12,color:'var(--teal)',background:'none',border:'none',cursor:'pointer',fontWeight:700,fontFamily:"'Figtree',sans-serif",textDecoration:'underline' }}>+ Add more</button>
                    )}
                  </div>
                  <button onClick={() => setSelected([])} style={{ fontSize:12,color:'var(--muted)',background:'none',border:'none',cursor:'pointer',fontFamily:"'Figtree',sans-serif",textDecoration:'underline' }}>Clear all</button>
                </div>
                <InsightStrip programs={selectedPrograms} />
                <CompareTable programs={selectedPrograms} onRemove={toggle} />
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
