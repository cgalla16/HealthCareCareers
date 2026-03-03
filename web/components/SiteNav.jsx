import Link from 'next/link';

/**
 * Shared top navigation bar.
 * Props:
 *   active — 'map' | 'careers' | 'programs'
 */
export default function SiteNav({ active }) {
  const links = [
    { href: '/map',                         id: 'map',      label: 'Salaries by State' },
    { href: '/careers/physical-therapists', id: 'careers',  label: 'Career Overview'   },
    { href: '/programs',                    id: 'programs', label: 'Compare Programs'  },
  ];

  return (
    <nav style={{
      background: 'white',
      borderBottom: '1.5px solid var(--rule)',
      padding: '0 40px',
      height: 58,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 100,
      boxShadow: '0 1px 4px rgba(28,25,23,0.05)',
    }}>
      {/* Logo */}
      <Link href="/map" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
        <div style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--teal)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15 }}>
          🏥
        </div>
        <span style={{ fontSize: 17, fontWeight: 800, color: 'var(--ink)', fontFamily: "'Fraunces', serif", letterSpacing: '-0.02em' }}>
          Health<span style={{ color: 'var(--teal)' }}>Career</span>
        </span>
      </Link>

      {/* Nav links */}
      <div style={{ display: 'flex', gap: 4 }}>
        {links.map(link => (
          <Link
            key={link.id}
            href={link.href}
            style={{
              padding: '6px 14px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: link.id === active ? 700 : 500,
              fontFamily: "'Figtree', sans-serif",
              color: link.id === active ? 'var(--teal)' : 'var(--ink2)',
              background: link.id === active ? 'var(--teal-lt)' : 'transparent',
              textDecoration: 'none',
              transition: 'all 0.15s',
            }}
          >
            {link.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
