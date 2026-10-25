import { Link } from 'react-router-dom';
import { useLang } from '../App';

const SUPPORT = 'https://t.me/BR_V2_Support';
const BOT = 'https://t.me/Brown_V2';
const OWNER = 'https://t.me/TariSmit';

export default function Footer() {
  const { lang } = useLang();

  return (
    <footer className="site-footer">
      <div className="container ft-inner">
        <div className="ft-brand">
          <svg width="28" height="28" viewBox="0 0 128 128">
            <defs>
              <linearGradient id="fg" x1="0" y1="0" x2="1" y2="1">
                <stop stopColor="var(--accent)" />
                <stop offset="1" stopColor="var(--accent2)" />
              </linearGradient>
            </defs>
            <rect width="128" height="128" rx="24" fill="var(--bg3)" />
            <text x="64" y="58" textAnchor="middle" fontFamily="system-ui" fontSize="34" fontWeight="800" fill="url(#fg)">BR</text>
            <text x="64" y="86" textAnchor="middle" fontFamily="system-ui" fontSize="20" fontWeight="700" fill="var(--text2)" letterSpacing="2">V2</text>
          </svg>
          <span>Brown V2</span>
        </div>

        <nav className="ft-nav">
          <Link to="/manual">{lang === 'ru' ? 'Мануал' : 'Manual'}</Link>
          <Link to="/price">{lang === 'ru' ? 'Цены' : 'Prices'}</Link>
          <Link to="/promo">{lang === 'ru' ? 'Промо' : 'Promo'}</Link>
          <Link to="/faq">FAQ</Link>
        </nav>

        <nav className="ft-links">
          <a href={BOT} target="_blank" rel="noreferrer">Telegram Bot</a>
          <a href={SUPPORT} target="_blank" rel="noreferrer">{lang === 'ru' ? 'Поддержка' : 'Support'}</a>
          <a href={OWNER} target="_blank" rel="noreferrer">{lang === 'ru' ? 'Владелец' : 'Owner'}</a>
        </nav>

        <p className="ft-copy">
          {lang === 'ru'
            ? '© 2025 Brown V2 — Telegram-сервис'
            : '© 2025 Brown V2 — Telegram Service'}
        </p>
      </div>
    </footer>
  );
}
