export const metadata = {
  title: {
    default: 'HealthCareer',
    template: '%s | HealthCareer',
  },
  description: 'Compare healthcare programs by pass rates, salary, and cost.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <style>{`
          @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700;9..144,900&family=Figtree:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

          *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

          :root {
            --cream:    #FAFAF7;
            --paper:    #F4F3EE;
            --rule:     #E5E3DB;
            --muted:    #9B9890;
            --ink:      #1C1917;
            --ink2:     #44403C;
            --teal:     #0D7A6B;
            --teal-lt:  #E6F4F1;
            --amber:    #B45309;
            --amber-lt: #FEF3C7;
            --blue:     #1D4ED8;
            --blue-lt:  #EFF6FF;
            --green:    #166534;
            --green-lt: #DCFCE7;
          }

          body { background: var(--cream); }

          .card-hover {
            transition: box-shadow 0.2s ease, transform 0.2s ease;
            cursor: pointer;
          }
          .card-hover:hover { box-shadow: 0 6px 24px rgba(28,25,23,0.10); transform: translateY(-2px); }
          .card-hover.sel   { box-shadow: 0 0 0 2px var(--teal), 0 6px 24px rgba(13,122,107,0.12); }

          .pill {
            display: inline-flex; align-items: center; gap: 5px;
            padding: 3px 10px; border-radius: 99px; font-size: 11px;
            font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
            font-family: 'Figtree', sans-serif;
          }

          .mrow-even > div { background: var(--paper) !important; }
          .mrow-odd  > div { background: white !important; }
          .metric-row:hover > div { background: var(--teal-lt) !important; transition: background 0.12s; }

          .bar-track { height: 5px; background: var(--rule); border-radius: 3px; overflow: hidden; margin-top: 7px; }
          .bar-fill  { height: 100%; border-radius: 3px; transition: width 0.9s cubic-bezier(.34,1.2,.64,1); }

          .cta { transition: all 0.18s cubic-bezier(.34,1.4,.64,1); cursor: pointer; }
          .cta:hover { transform: scale(1.03); box-shadow: 0 6px 20px rgba(13,122,107,0.25); }

          .fade { animation: fu 0.35s ease both; }
          @keyframes fu { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
          .d1{animation-delay:.04s} .d2{animation-delay:.08s} .d3{animation-delay:.12s} .d4{animation-delay:.16s}

          ::-webkit-scrollbar { width:4px; height:4px; }
          ::-webkit-scrollbar-track { background: var(--paper); }
          ::-webkit-scrollbar-thumb { background: var(--rule); border-radius:2px; }
        `}</style>
      </head>
      <body>{children}</body>
    </html>
  );
}
