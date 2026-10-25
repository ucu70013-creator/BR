import { useState } from 'react';
import { useLang } from '../App';

const SUPPORT = 'https://t.me/BR_V2_Support';
const BOT = 'https://t.me/Brown_V2';
const OWNER = 'https://t.me/TariSmit';
const CHANNEL = 'https://t.me/+3u8scLryHxdmNDUy';

const T = {
  ru: {
    label: 'FAQ',
    title: 'Вопросы и ответы',
    sub: 'Самые частые вопросы о Brown V2',
    faqs: [
      ['Что такое Brown V2?', 'Brown V2 — Telegram-бот для массовой подачи жалоб на аккаунты, боты, каналы и контент в Telegram. Использует несколько методов: ботнет, web-жалобы, email-рассылки, EU DSA, TIDA и другие.'],
      ['Как начать пользоваться?', 'Откройте бота @Brown_V2, пройдите капчу, подпишитесь на каналы, затем выберите нужный метод в меню. Для платных функций нужна подписка.'],
      ['Какие методы доступны без подписки?', 'Без подписки доступны бесплатные репорты (из колеса удачи или промокодов). С подпиской открываются все методы.'],
      ['Как оплатить подписку?', 'Через бота — оплата в USDT (криптовалюта). Через карту — написать @TariSmit. Цены указаны на странице Цены.'],
      ['Что такое Премиум?', 'Премиум — дополнение к базовой подписке, открывает эксклюзивные методы и улучшенные лимиты.\n\n🔓 Эксклюзивные методы (только Премиум):\n• 👑 Премиум-ботнет — в 2-3x выше доходимость через Telegram Premium аккаунты\n• 🌐 Universal метод — продвинутая универсальная атака\n• 💀 Снос сессий — сброс активных сессий цели\n• 🌍 Домен киллер — блокировка доменов цели\n\n📈 Улучшенные лимиты:\n• 5 мониторов одновременно (вместо 3 у базовой)\n• Мониторинг до 24ч (вместо 12ч у базовой)\n• Пробив — без ограничений (вместо 5 запросов/ч)\n• Приоритет в очереди отправки'],
      ['Что такое зеркала?', 'Зеркало — копия бота с вашим токеном. Если основной бот заблокирован — используй зеркало. Полный функционал сохраняется.'],
      ['Как работает мониторинг?', 'После атаки бот каждые 10 минут проверяет цель. Как только она снесена — приходит уведомление 🔴. Обычная подписка: 3 монитора по 12 часов. Премиум: 5 мониторов по 24 часа.'],
      ['Есть ли гарантия сноса?', 'Нет — результат зависит от активности аккаунта цели, типа нарушения и реакции Telegram. Мы предоставляем инструмент, результат не гарантируется.'],
      ['Что такое реферальная система?', 'За каждого приглашённого друга — +1 реферал. За 10 рефералов — 1 день подписки бесплатно. Также 10% от покупки подписки вашим рефералом начисляется вам.'],
      ['Куда обращаться по проблемам?', 'В официальную поддержку: @BR_V2_Support. По вопросам оплаты: @TariSmit.'],
    ],
    contacts: 'Контакты',
    openBot: 'Бот',
    support: 'Поддержка',
    owner: 'Владелец',
    channel: 'Канал',
    ctaTitle: 'Не нашёл ответ?',
    ctaSub: 'Напиши в поддержку — ответим быстро.',
    ctaBtn: 'Написать в поддержку',
  },
  en: {
    label: 'FAQ',
    title: 'Questions & Answers',
    sub: 'The most common questions about Brown V2',
    faqs: [
      ['What is Brown V2?', 'Brown V2 is a Telegram bot for mass reporting of accounts, bots, channels, and content on Telegram. It uses multiple methods: botnet, web reports, email campaigns, EU DSA, TIDA, and more.'],
      ['How do I get started?', 'Open the bot @Brown_V2, pass the captcha, subscribe to the channels, then choose the desired method from the menu. Paid methods require a subscription.'],
      ['What is available without a subscription?', 'Free reports (from the fortune wheel or promo codes) are available without a subscription. A subscription unlocks all methods.'],
      ['How do I pay for a subscription?', 'Through the bot — payment in USDT (crypto). By card — message @TariSmit. Prices are on the Prices page.'],
      ['What is Premium?', 'Premium is an add-on to your base subscription — unlocks exclusive methods and higher limits.\n\n🔓 Exclusive methods (Premium only):\n• 👑 Premium Botnet — 2-3x higher delivery via Telegram Premium accounts\n• 🌐 Universal method — advanced multi-vector attack\n• 💀 Session Knockdown — force-logout all active sessions of the target\n• 🌍 Domain Killer — block the target\'s domains\n\n📈 Upgraded limits:\n• 5 simultaneous monitors (instead of 3 on base)\n• Monitoring up to 24h (instead of 12h on base)\n• Lookup — unlimited queries (instead of 5/hour)\n• Priority in the send queue'],
      ['What are mirrors?', 'A mirror is a copy of the bot with your token. If the main bot is blocked — use a mirror. Full functionality is preserved.'],
      ['How does monitoring work?', 'After an attack, the bot checks the target every 10 minutes. When it is taken down, you receive a 🔴 notification. Regular subscription: 3 monitors for 12 hours. Premium: 5 monitors for 24 hours.'],
      ['Is a takedown guaranteed?', 'No — the result depends on the target account\'s activity, the type of violation, and Telegram\'s response. We provide the tool; results are not guaranteed.'],
      ['What is the referral system?', 'For each invited friend — +1 referral. For 10 referrals — 1 free day of subscription. Also, 10% of a subscription purchase by your referral is credited to you.'],
      ['Where to go for issues?', 'Official support: @BR_V2_Support. Payment questions: @TariSmit.'],
    ],
    contacts: 'Contacts',
    openBot: 'Bot',
    support: 'Support',
    owner: 'Owner',
    channel: 'Channel',
    ctaTitle: "Didn't find an answer?",
    ctaSub: 'Message support — we reply fast.',
    ctaBtn: 'Contact support',
  },
};

export default function FAQ() {
  const { lang } = useLang();
  const t = T[lang];
  const [open, setOpen] = useState<number | null>(0);

  return (
    <div className="page-inner container">
      <div className="page-head">
        <div className="sec-label">{t.label}</div>
        <h1>{t.title}</h1>
        <p>{t.sub}</p>
      </div>

      {/* Contacts */}
      <div className="contact-row">
        <a href={BOT} target="_blank" rel="noreferrer" className="contact-chip">
          🤖{t.openBot}
        </a>
        <a href={SUPPORT} target="_blank" rel="noreferrer" className="contact-chip">
          💬{t.support}
        </a>
        <a href={OWNER} target="_blank" rel="noreferrer" className="contact-chip">
          👑{t.owner}
        </a>
        <a href={CHANNEL} target="_blank" rel="noreferrer" className="contact-chip">
          📢{t.channel}
        </a>
      </div>

      {/* FAQ accordion */}
      <div className="accordion">
        {t.faqs.map(([q, a], i) => (
          <div key={i} className={`acc-item${open === i ? ' open' : ''}`}>
            <button className="acc-head" onClick={() => setOpen(open === i ? null : i)}>
              <span className="acc-num">{String(i + 1).padStart(2, '0')}</span>
              <span className="acc-name">{q}</span>
              <svg className="acc-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6"/></svg>
            </button>
            {open === i && (
              <div className="acc-body">
                <p style={{ whiteSpace: 'pre-line' }}>{a}</p>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* CTA */}
      <div className="faq-cta">
        <h3>{t.ctaTitle}</h3>
        <p>{t.ctaSub}</p>
        <a href={SUPPORT} target="_blank" rel="noreferrer" className="btn-primary">{t.ctaBtn}</a>
      </div>
    </div>
  );
}
