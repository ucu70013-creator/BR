import { useLang } from '../App';

const SUPPORT = 'https://t.me/TariSmit';
const BOT = 'https://t.me/Brown_V2';

const T = {
  ru: {
    label: 'Тарифы',
    title: 'Выбери свой тариф',
    sub: 'Один платёж — доступ активируется сразу. Без скрытых условий.',
    popular: 'Выгоднее всего',
    choose: 'Выбрать',
    chooseBot: 'Купить в боте',
    buyCard: 'Оплатить картой',
    cardNote: 'Оплата через владельца: ',
    premNote: '⚠️ Премиум покупается как дополнение к подписке',
    currency: '₽ / $',
    plans: [
      { id: '1d', name: '1 день', rub: '100', usd: '1', icon: '⚡', feat: ['Все методы', 'Ботнет', 'Web', 'Mail'] },
      { id: '3d', name: '3 дня', rub: '175', usd: '2', icon: '⚡', feat: ['Все методы', 'Ботнет', 'Web', 'Mail'] },
      { id: '7d', name: '7 дней', rub: '350', usd: '4', icon: '✨', feat: ['Все методы', 'Зеркала (бонус)', 'Мониторинг x3'] },
      { id: '30d', name: '30 дней', rub: '700', usd: '8', icon: '✨', feat: ['Все методы', 'Зеркала (бонус)', 'Мониторинг x3'] },
      { id: 'forever', name: 'Навсегда', rub: '500', usd: '6', icon: '∞', popular: true, discount: '-70%', feat: ['Все методы', 'Навсегда', 'Все обновления'] },
      { id: 'premium', name: 'Премиум', rub: '400', usd: '5', icon: '👑', discount: '-50%', feat: ['Премиум-аккаунты', 'Мониторинг x5 (24ч)', 'Приоритет'] },
    ],
  },
  en: {
    label: 'Pricing',
    title: 'Choose your plan',
    sub: 'One payment — instant access. No hidden terms.',
    popular: 'Best value',
    choose: 'Choose',
    chooseBot: 'Buy in bot',
    buyCard: 'Pay by card',
    cardNote: 'Pay via owner: ',
    premNote: '⚠️ Premium is an add-on to an existing subscription',
    currency: '₽ / $',
    plans: [
      { id: '1d', name: '1 day', rub: '100', usd: '1', icon: '⚡', feat: ['All methods', 'Botnet', 'Web', 'Mail'] },
      { id: '3d', name: '3 days', rub: '175', usd: '2', icon: '⚡', feat: ['All methods', 'Botnet', 'Web', 'Mail'] },
      { id: '7d', name: '7 days', rub: '350', usd: '4', icon: '✨', feat: ['All methods', 'Mirrors (bonus)', 'Monitoring x3'] },
      { id: '30d', name: '30 days', rub: '700', usd: '8', icon: '✨', feat: ['All methods', 'Mirrors (bonus)', 'Monitoring x3'] },
      { id: 'forever', name: 'Forever', rub: '500', usd: '6', icon: '∞', popular: true, discount: '-70%', feat: ['All methods', 'Lifetime access', 'All updates'] },
      { id: 'premium', name: 'Premium', rub: '400', usd: '5', icon: '👑', discount: '-50%', feat: ['Premium accounts', 'Monitoring x5 (24h)', 'Priority'] },
    ],
  },
};

export default function Price() {
  const { lang } = useLang();
  const t = T[lang];

  return (
    <div className="page-inner container">
      <div className="page-head">
        <div className="sec-label">{t.label}</div>
        <h1>{t.title}</h1>
        <p>{t.sub}</p>
      </div>

      <div className="price-grid">
        {t.plans.map(p => (
          <article key={p.id} className={`price-card${(p as any).popular ? ' featured' : ''}`}>
            {(p as any).popular && <div className="pop-badge">⭐ {t.popular}</div>}
            {(p as any).discount && <span className="disc-badge">{(p as any).discount}</span>}
            <div className="pc-icon">{p.icon}</div>
            <h3>{p.name}</h3>
            <div className="pc-price">
              <span className="rub">{p.rub} ₽</span>
              <span className="usd">/ {p.usd} $</span>
            </div>
            <ul className="pc-feats">
              {p.feat.map(f => <li key={f}><span className="chk">✓</span>{f}</li>)}
            </ul>
            <div className="pc-btns">
              <a href={BOT} target="_blank" rel="noreferrer" className="btn-primary sm">{t.chooseBot}</a>
            </div>
          </article>
        ))}
      </div>

    </div>
  );
}
