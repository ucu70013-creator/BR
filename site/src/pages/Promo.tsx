import { useEffect, useRef, useState } from 'react';
import { useLang } from '../App';
import { Promo as PromoType } from '../api';

const BOT = 'https://t.me/Brown_V2';

const T = {
  ru: {
    label: 'Промокоды',
    title: 'Активные промокоды',
    sub: 'Используй промокод в боте для получения подписки или бесплатных репортов',
    how: 'Как активировать',
    howSteps: [
      'Откройте бота',
      'Получите личное зеркало',
      'Нажмите на Бонусы',
      'Промокод',
      'Введите код из списка ниже',
    ],
    openBot: 'Открыть бота',
    active: 'Активен',
    inactive: 'Неактивен',
    noPromos: 'Активных промокодов пока нет',
    noPromosSub: 'Следи за обновлениями в канале',
    expires: 'Действует до',
    noExpiry: 'Бессрочно',
    copy: 'Скопировать',
    copied: 'Скопировано!',
    days: (n: number) => `${n} ${n === 1 ? 'день' : n < 5 ? 'дня' : 'дней'}`,
    acts: (n: number) => `${n} активаций`,
    typeNormal: 'Обычный',
    typePremium: 'Премиум',
    typeReports: 'Репорты',
  },
  en: {
    label: 'Promo Codes',
    title: 'Active promo codes',
    sub: 'Use a promo code in the bot to get a subscription or free reports',
    how: 'How to activate',
    howSteps: [
      'Open the bot',
      'Get your personal mirror',
      'Tap Bonuses',
      'Promo Code',
      'Enter the code from the list below',
    ],
    openBot: 'Open bot',
    active: 'Active',
    inactive: 'Inactive',
    noPromos: 'No active promo codes right now',
    noPromosSub: 'Follow the channel for updates',
    expires: 'Expires',
    noExpiry: 'No expiry',
    copy: 'Copy',
    copied: 'Copied!',
    days: (n: number) => `${n} day${n !== 1 ? 's' : ''}`,
    acts: (n: number) => `${n} uses`,
    typeNormal: 'Regular',
    typePremium: 'Premium',
    typeReports: 'Reports',
  },
};

export default function Promo() {
  const { lang } = useLang();
  const t = T[lang];
  const [promos, setPromos] = useState<PromoType[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<number | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let es: EventSource;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      es = new EventSource('/api/promos/stream');
      esRef.current = es;

      es.onmessage = (e) => {
        try {
          setPromos(JSON.parse(e.data));
        } catch {}
        setLoading(false);
      };

      es.onerror = () => {
        es.close();
        // Reconnect after 3 seconds on error
        retryTimer = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      clearTimeout(retryTimer);
      es?.close();
    };
  }, []);

  const copyCode = (id: number, code: string) => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  const typeLabel = (type: string) => {
    if (type === 'premium') return t.typePremium;
    if (type === 'reports') return t.typeReports;
    return t.typeNormal;
  };

  return (
    <div className="page-inner container">
      <div className="page-head">
        <div className="sec-label">{t.label}</div>
        <h1>{t.title}</h1>
        <p>{t.sub}</p>
      </div>

      {/* How to */}
      <div className="how-card">
        <h3>🎁 {t.how}</h3>
        <ol>
          {t.howSteps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
        <a href={BOT} target="_blank" rel="noreferrer" className="btn-primary sm">{t.openBot}</a>
      </div>

      {/* Promo list */}
      {loading ? (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      ) : promos.length === 0 ? (
        <div className="empty-state">
          <span>🎁</span>
          <h3>{t.noPromos}</h3>
          <p>{t.noPromosSub}</p>
        </div>
      ) : (
        <div className="promo-list">
          {promos.map(p => (
            <div key={p.id} className={`promo-card${p.active ? '' : ' inactive'}`}>
              <div className="pc-header">
                <div>
                  <h3>{p.title}</h3>
                  {p.description && <p>{p.description}</p>}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                  <span className={`status-badge ${p.active ? 'active' : 'off'}`}>
                    {p.active ? t.active : t.inactive}
                  </span>
                  <span className="status-badge" style={{ opacity: 0.75 }}>{typeLabel(p.promo_type)}</span>
                </div>
              </div>
              <div className="pc-code-row">
                <code className="promo-code">{p.code}</code>
                <button className="copy-btn" onClick={() => copyCode(p.id, p.code)} disabled={!p.active}>
                  {copied === p.id ? t.copied : t.copy}
                </button>
              </div>
              <div className="pc-meta">
                <span>{t.days(p.days)}</span>
                <span style={{ margin: '0 6px', opacity: 0.4 }}>·</span>
                <span>{t.acts(p.activations)}</span>
                <span style={{ margin: '0 6px', opacity: 0.4 }}>·</span>
                <span>
                  {p.expires_at
                    ? `${t.expires}: ${new Date(p.expires_at).toLocaleDateString(lang === 'ru' ? 'ru-RU' : 'en-US')}`
                    : t.noExpiry}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
