import { OCCUPATIONS } from '@/lib/constants';
import { getMapData } from '@/lib/db';
import UsaMap from '@/components/UsaMap';
import SiteNav from '@/components/SiteNav';

export const metadata = { title: 'Salaries by State' };

export default function MapPage() {
  // Pre-load all 4 occupation datasets at build time — 4×52=208 rows total
  const allData = Object.fromEntries(
    OCCUPATIONS.map(occ => [occ.slug, getMapData(occ.name)])
  );

  return (
    <div style={{ minHeight: '100vh', background: 'var(--cream)' }}>
      <SiteNav active="map" />
      <UsaMap allData={allData} />
    </div>
  );
}
