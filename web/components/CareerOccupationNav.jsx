'use client';

import { useRouter } from 'next/navigation';
import OccupationNav from './OccupationNav';

/**
 * Thin client wrapper for OccupationNav on career pages.
 * Navigates to /careers/[slug] on tab click.
 */
export default function CareerOccupationNav({ activeSlug }) {
  const router = useRouter();
  return (
    <OccupationNav
      activeSlug={activeSlug}
      onChange={slug => router.push(`/careers/${slug}`)}
    />
  );
}
