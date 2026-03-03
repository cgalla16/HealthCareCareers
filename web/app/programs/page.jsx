import { getPrograms } from '@/lib/db';
import ProgramComparison from '@/components/ProgramComparison';

export const metadata = { title: 'Compare Programs' };

export default function ProgramsPage() {
  const programs = getPrograms();
  return <ProgramComparison programs={programs} />;
}
