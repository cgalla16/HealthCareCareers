import { notFound } from 'next/navigation';

import { SLUGS, OCCUPATIONS } from '@/lib/constants';
import { getNationalStats, getWorkSettings, getProgramStats } from '@/lib/db';
import { S } from '@/lib/styles';

import SiteNav from '@/components/SiteNav';
import CareerOccupationNav from '@/components/CareerOccupationNav';
import KpiRow from '@/components/KpiRow';
import SalaryPercentileBar from '@/components/SalaryPercentileBar';
import WorkSettingsTable from '@/components/WorkSettingsTable';
import ProgramStatsRow from '@/components/ProgramStatsRow';

export function generateStaticParams() {
  return OCCUPATIONS.map(occ => ({ slug: occ.slug }));
}

export async function generateMetadata({ params }) {
  const { slug } = await params;
  const name = SLUGS[slug];
  if (!name) return {};
  return { title: name };
}

export default async function CareerPage({ params }) {
  const { slug } = await params;
  const name = SLUGS[slug];
  if (!name) notFound();

  const ns = getNationalStats(name);
  const ws = getWorkSettings(name);
  const ps = getProgramStats(name);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--cream)', fontFamily: "'Figtree', sans-serif" }}>
      <SiteNav active="careers" />

      {/* Page header */}
      <div style={{ background: 'white', borderBottom: '1.5px solid var(--rule)', padding: '36px 40px 28px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--teal)', marginBottom: 10, fontFamily: "'Figtree', sans-serif" }}>
            Career Overview
          </div>
          <h1 style={{ fontSize: 36, fontWeight: 900, fontFamily: "'Fraunces', serif", color: 'var(--ink)', letterSpacing: '-0.02em', marginBottom: 8 }}>
            {name}
          </h1>
          <p style={{ fontSize: 13, color: 'var(--muted)' }}>
            Salary data — BLS OEWS May 2024
          </p>
          <div style={{ marginTop: 20 }}>
            <CareerOccupationNav activeSlug={slug} />
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ ...S.pageWrapper, maxWidth: 1100 }}>

        {/* KPIs */}
        <h2 style={S.sectionHeading}>At a Glance</h2>
        <KpiRow
          employment={ns?.employment}
          median={ns?.median}
          growthPct={ns?.blsGrowthPct}
          numPrograms={ps.numPrograms}
        />

        <hr style={S.divider} />

        {/* Salary percentiles */}
        <h2 style={S.sectionHeading}>Salary Distribution</h2>
        <SalaryPercentileBar
          p10={ns?.p10}
          p25={ns?.p25}
          median={ns?.median}
          p75={ns?.p75}
          p90={ns?.p90}
        />

        <hr style={S.divider} />

        {/* Work settings */}
        <h2 style={S.sectionHeading}>Salary by Work Setting</h2>
        <WorkSettingsTable rows={ws} />

        <hr style={S.divider} />

        {/* Program stats */}
        <h2 style={S.sectionHeading}>Program Statistics</h2>
        <ProgramStatsRow
          totalGraduates={ps.totalGraduates}
          avgSize={ps.avgSize}
          numPrograms={ps.numPrograms}
        />

      </div>
    </div>
  );
}
