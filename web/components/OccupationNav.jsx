'use client';

import { S } from '@/lib/styles';
import { OCCUPATIONS } from '@/lib/constants';

/**
 * Shared occupation tab strip.
 * Props:
 *   activeSlug  — which tab is currently highlighted
 *   onChange    — callback(slug) — parent decides navigation (router.push or setState)
 */
export default function OccupationNav({ activeSlug, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {OCCUPATIONS.map(occ => (
        <button
          key={occ.slug}
          onClick={() => onChange(occ.slug)}
          style={occ.slug === activeSlug ? S.pillActive : S.pill}
        >
          {occ.name}
        </button>
      ))}
    </div>
  );
}
