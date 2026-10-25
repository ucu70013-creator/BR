import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { themes } from '../themes';
import { useLang } from '../App';

const BOT_URL = 'https://t.me/Brown_V2';

const NAV_RU = [
  { path: '/', label: 'Главная' },
  { path: '/manual', label: 'Мануал' },
  { path: '/price', label: 'Цены' },
  { path: '/promo', label: 'Промо' },
  { path: '/faq', label: 'FAQ' },
];
const NAV_EN = [
  { path: '/', label: 'Home' },
  { path: '/manual', label: 'Manual' },
  { path: '/price', label: 'Prices' },
  { path: '/promo', label: 'Promo' },
  { path: '/faq', label: 'FAQ' },
];

export default function Header() {
  const { lang, setLang, themeId, setThemeId } = useLang();
  const [open, setOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
  const loc = useLocation();

  const nav = lang === 'ru' ? NAV_RU : NAV_EN;
  const current = themes.find(t => t.id === themeId)!;

  return (
    <header className="site-header">
      <div className="container hd-inner">
        <Link to="/" className="brand" onClick={() => setOpen(false)}>
          <svg width="32" height="32" viewBox="0 0 128 128">
            <defs>
              <linearGradient id="hg" x1="0" y1="0" x2="1" y2="1">
                <stop stopColor="var(--accent)" />
                <stop offset="1" stopColor="var(--accent2)" />
              </linearGradient>
            </defs>
            <rect width="128" height="128" rx="24" fill="var(--bg3)" />
            <text x="64" y="58" textAnchor="middle" fontFamily="system-ui" fontSize="34" fontWeight="800" fill="url(#hg)">BR</text>
            <text x="64" y="86" textAnchor="middle" fontFamily="system-ui" fontSize="20" fontWeight="700" fill="var(--text2)" letterSpacing="2">V2</text>
          </svg>
          <span className="brand-name">Brown V2</span>
        </Link>

        <nav className={`hd-nav${open ? ' open' : ''}`}>
          {nav.map(n => (
            <Link
              key={n.path}
              to={n.path}
              className={`hd-link${loc.pathname === n.path ? ' active' : ''}`}
              onClick={() => setOpen(false)}
            >
              {n.label}
            </Link>
          ))}
        </nav>

        <div className="hd-right">
          {/* Theme picker */}
          <div className="theme-wrap">
            <button
              className="theme-btn"
              onClick={() => setThemeOpen(!themeOpen)}
              title={lang === 'ru' ? 'Тема' : 'Theme'}
            >
              <span className="swatch" style={{ background: `linear-gradient(135deg, ${current.preview[0]}, ${current.preview[1]})` }} />
            </button>
            {themeOpen && (
              <>
                <div className="theme-backdrop" onClick={() => setThemeOpen(false)} />
                <div className="theme-dropdown">
                  {themes.map(th => (
                    <button
                      key={th.id}
                      className={`theme-opt${th.id === themeId ? ' sel' : ''}`}
                      onClick={() => { setThemeId(th.id); setThemeOpen(false); }}
                    >
                      <span className="swatch sm" style={{ background: `linear-gradient(135deg, ${th.preview[0]}, ${th.preview[1]})` }} />
                      <span>{th.name[lang]}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Lang */}
          <div className="lang-sw">
            <button className={lang === 'ru' ? 'active' : ''} onClick={() => setLang('ru')}>RU</button>
            <span>/</span>
            <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
          </div>

          <a href={BOT_URL} target="_blank" rel="noreferrer" className="hd-cta">
            {lang === 'ru' ? 'Открыть бота' : 'Open bot'}
          </a>
        </div>

        <button className="burger" onClick={() => setOpen(!open)} aria-label="menu">
          <span /><span /><span />
        </button>
      </div>

      {open && (
        <div className="hd-mobile-panel">
          {nav.map(n => (
            <Link key={n.path} to={n.path} className={`hd-link${loc.pathname === n.path ? ' active' : ''}`} onClick={() => setOpen(false)}>
              {n.label}
            </Link>
          ))}
          <a href={BOT_URL} target="_blank" rel="noreferrer" className="hd-cta" onClick={() => setOpen(false)}>
            {lang === 'ru' ? 'Открыть бота' : 'Open bot'}
          </a>
        </div>
      )}
    </header>
  );
}
