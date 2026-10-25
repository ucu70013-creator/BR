import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useLang } from '../App';
import { FeatureIcon } from '../components/Icons';
import { api, Mirror, Review } from '../api';

const BOT = 'https://t.me/Brown_V2';
const SUPPORT = 'https://t.me/BR_V2_Support';

const T = {
  ru: {
    badge: 'Официальный сайт Brown V2',
    h1a: 'Твой доступ к Telegram.',
    h1b: 'Быстро. Чисто. Без лишнего.',
    sub: 'Brown V2 — Telegram-бот для массовой подачи жалоб с активными зеркалами, поддержкой 24/7 и понятным интерфейсом.',
    open: 'Открыть бота',
    howto: 'Как пользоваться',
    users: 'пользователей в боте',
    methods: 'методов',
    support: 'Поддержка 24/7',
    mirrors: 'Активные зеркала',
    mirrorsSub: 'Если основной бот недоступен — используй одно из зеркал. Полный функционал.',
    noMirrors: 'Зеркала обновляются администратором',
    active: 'Активно',
    dead: 'Не работает',
    reviewsTitle: 'Отзывы',
    reviewsSub: 'Реальные отзывы пользователей',
    noReviews: 'Отзывы скоро появятся',
    ctaTitle: 'Готов начать?',
    ctaSub: 'Открой бота и выбери подходящий тариф',
    ctaBtn: 'Запустить бота',
    ctaSupport: 'Написать в поддержку',
    featTitle: 'Почему Brown V2',
    feat: [
      ['zap',    'Быстрый запуск',        'Стартуй за 30 секунд — без сложной регистрации'],
      ['lock',   'Прозрачные условия',    'Цены и сроки указаны заранее, скрытых платежей нет'],
      ['link',   'Зеркала',               'Работаем даже если основной бот недоступен'],
      ['cpu',    'ИИ-методы',             'TIDA и DSA используют ИИ для генерации жалоб'],
      ['bell',   'Мониторинг',            'Уведомление когда цель будет снесена'],
      ['gift',   'Бесплатные репорты',    'Колесо фортуны и промокоды каждую неделю'],
      ['search', 'Пробив',                'Поиск по открытым базам: телефон, ФИО, email, авто и многое другое'],
    ],
    marquee: [
      ['⚡', '17 методов'], ['🔒', 'Прозрачные условия'], ['🪞', 'Активные зеркала'],
      ['🤖', 'ИИ-методы TIDA и DSA'], ['🔔', 'Мониторинг цели'], ['🎁', 'Бесплатные репорты'],
      ['🔍', 'Пробив по базам'], ['💳', 'Оплата СБП'], ['24/7', 'Поддержка'],
    ],
  },
  en: {
    badge: 'Official Brown V2 website',
    h1a: 'Your Telegram access.',
    h1b: 'Fast. Clean. No noise.',
    sub: 'Brown V2 — a Telegram bot for mass reporting with active mirrors, 24/7 support, and a simple interface.',
    open: 'Open bot',
    howto: 'How it works',
    users: 'users in the bot',
    methods: 'methods',
    support: '24/7 support',
    mirrors: 'Active mirrors',
    mirrorsSub: 'If the main bot is unavailable — use a mirror. Full functionality.',
    noMirrors: 'Mirrors are managed by the administrator',
    active: 'Active',
    dead: 'Down',
    reviewsTitle: 'Reviews',
    reviewsSub: 'Real user feedback',
    noReviews: 'Reviews coming soon',
    ctaTitle: 'Ready to start?',
    ctaSub: 'Open the bot and choose a plan',
    ctaBtn: 'Launch bot',
    ctaSupport: 'Contact support',
    featTitle: 'Why Brown V2',
    feat: [
      ['zap',    'Fast start',    'Launch in 30 seconds — no complex registration'],
      ['lock',   'Clear terms',   'Prices upfront, no hidden fees'],
      ['link',   'Mirrors',       'Works even when the main bot is down'],
      ['cpu',    'AI methods',    'TIDA and DSA use AI to generate reports'],
      ['bell',   'Monitoring',    'Get notified when the target is taken down'],
      ['gift',   'Free reports',  'Fortune wheel and promo codes weekly'],
      ['search', 'Lookup',        'Search open databases: phone, name, email, car and more'],
    ],
    marquee: [
      ['⚡', '17 methods'], ['🔒', 'Clear terms'], ['🪞', 'Active mirrors'],
      ['🤖', 'AI methods TIDA & DSA'], ['🔔', 'Target monitoring'], ['🎁', 'Free reports'],
      ['🔍', 'Database lookup'], ['💳', 'SBP payments'], ['24/7', 'Support'],
    ],
  },
};

export default function Home() {
  const { lang } = useLang();
  const t = T[lang];
  const [userCount, setUserCount] = useState<number | null>(null);
  const [mirrors, setMirrors] = useState<Mirror[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    api.stats().then(s => setUserCount(s.users)).catch(() => {});
    api.mirrors().then(setMirrors).catch(() => {});
    api.reviews().then(setReviews).catch(() => {});
  }, []);

  useEffect(() => {
    const obs = new IntersectionObserver(
      entries => entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); }),
      { threshold: 0.1 }
    );
    document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, [mirrors, reviews]);

  /* Canvas particle animation — disabled on mobile to save GPU */
  useEffect(() => {
    const isMobile = window.matchMedia('(max-width: 768px)').matches;
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const canvas = canvasRef.current;
    if (!canvas || isMobile || prefersReduced) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let W = 0, H = 0;
    const resize = () => {
      W = canvas.width = canvas.offsetWidth;
      H = canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    type P = { x: number; y: number; vx: number; vy: number; r: number; alpha: number; cr: number; cg: number; cb: number };
    const palette = [[124,58,255],[56,189,248],[6,214,160],[167,139,250]];
    const pts: P[] = Array.from({ length: 35 }, () => {
      const [cr,cg,cb] = palette[Math.floor(Math.random()*palette.length)];
      return { x: Math.random()*1200, y: Math.random()*600, vx:(Math.random()-.5)*.35, vy:(Math.random()-.5)*.35, r:Math.random()*1.6+.4, alpha:Math.random()*.4+.08, cr,cg,cb };
    });

    let raf: number;
    const draw = () => {
      ctx.clearRect(0,0,W,H);
      for (const p of pts) {
        p.x += p.vx; p.y += p.vy;
        if (p.x<0) p.x=W; if (p.x>W) p.x=0;
        if (p.y<0) p.y=H; if (p.y>H) p.y=0;
        ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
        ctx.fillStyle=`rgba(${p.cr},${p.cg},${p.cb},${p.alpha})`; ctx.fill();
      }
      for (let i=0;i<pts.length;i++) for (let j=i+1;j<pts.length;j++) {
        const dx=pts[i].x-pts[j].x, dy=pts[i].y-pts[j].y;
        const d=Math.sqrt(dx*dx+dy*dy);
        if (d<100) { ctx.beginPath(); ctx.strokeStyle=`rgba(124,58,255,${.08*(1-d/100)})`; ctx.lineWidth=.5; ctx.moveTo(pts[i].x,pts[i].y); ctx.lineTo(pts[j].x,pts[j].y); ctx.stroke(); }
      }
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); };
  }, []);

  const mq = [...t.marquee, ...t.marquee];

  return (
    <div className="home">
      {/* Hero */}
      <section className="hero-section">
        <canvas ref={canvasRef} className="hero-canvas" />
        <div className="container hero">
          <div className="hero-body">
            <div className="eyebrow reveal visible">
              <span className="dot" />
              {t.badge}
            </div>
            <h1 className="reveal visible" style={{ transitionDelay: '0.05s' }}>
              {t.h1a}<br />
              <span className="accent-text">{t.h1b}</span>
            </h1>
            <p className="hero-sub reveal visible" style={{ transitionDelay: '0.12s' }}>{t.sub}</p>
            <div className="hero-btns reveal visible" style={{ transitionDelay: '0.18s' }}>
              <a href={BOT} target="_blank" rel="noreferrer" className="btn-primary">
                {t.open}
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              </a>
              <Link to="/manual" className="btn-ghost">{t.howto}</Link>
            </div>
            <div className="hero-stats reveal visible" style={{ transitionDelay: '0.25s' }}>
              <div className="hstat">
                <strong>{userCount !== null ? userCount.toLocaleString() : '—'}</strong>
                <span>{t.users}</span>
              </div>
              <div className="hstat-div" />
              <div className="hstat"><strong>17</strong><span>{t.methods}</span></div>
              <div className="hstat-div" />
              <div className="hstat"><strong>24/7</strong><span>{t.support}</span></div>
            </div>
          </div>

          <div className="hero-visual">
            <div className="glow-orb" />
            <div className="orbit-ring orbit-ring-1"><span className="orbit-dot" /></div>
            <div className="orbit-ring orbit-ring-2"><span className="orbit-dot orbit-dot-2" /></div>
            <div className="logo-frame logo-img-frame">
              <img src="/logo.png" alt="Brown V2" width="220" height="220" style={{ borderRadius:'50%', display:'block' }} />
            </div>
            <div className="float-chip top">
              <span className="pulse-dot" />
              <span>Brown V2 — Онлайн</span>
            </div>
            <div className="float-chip bot">
              <span style={{ fontSize:'1rem' }}>👥</span>
              <strong>{userCount !== null ? userCount.toLocaleString() : '...'}</strong>
              <span style={{ color:'var(--text2)', fontWeight:400 }}>{t.users}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Marquee */}
      <div className="marquee-strip">
        <div className="marquee-track">
          {mq.map(([icon, label], i) => (
            <span key={i}><em>{icon}</em>{label}</span>
          ))}
        </div>
      </div>

      {/* Features */}
      <section className="section container">
        <div className="sec-head reveal">
          <div className="sec-label">Brown V2</div>
          <h2>{t.featTitle}</h2>
        </div>
        <div className="feat-grid">
          {t.feat.map(([icon, title, desc], i) => (
            <div className={`feat-card feat-card-anim feat-anim-d${Math.min(i+1,7)}`} key={title}>
              <div className="feat-icon"><FeatureIcon name={icon} /></div>
              <h3>{title}</h3>
              <p>{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Mirrors */}
      <section className="section section-alt">
        <div className="container">
          <div className="sec-head reveal">
            <div className="sec-label">ЗЕРКАЛА</div>
            <h2>{t.mirrors}</h2>
            <p>{t.mirrorsSub}</p>
          </div>
          {mirrors.length === 0 ? (
            <p className="empty-note">{t.noMirrors}</p>
          ) : (
            <div className="mirror-list">
              {mirrors.map((m, i) => (
                <a key={m.id} href={m.url} target="_blank" rel="noreferrer"
                   className={`mirror-row ${m.status} reveal reveal-d${Math.min(i+1,7)}`}>
                  <span className={`m-dot ${m.status}`} />
                  <div className="m-info">
                    <strong>{m.name}</strong>
                    <small>{m.url.replace('https://t.me/','t.me/')}</small>
                  </div>
                  <span className={`m-status-label ${m.status}`}>
                    {m.status === 'active' ? t.active : t.dead}
                  </span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Reviews */}
      {reviews.length > 0 && (
        <section className="section container">
          <div className="sec-head reveal">
            <div className="sec-label">ОТЗЫВЫ</div>
            <h2>{t.reviewsTitle}</h2>
            <p>{t.reviewsSub}</p>
          </div>
          <div className="reviews-grid">
            {reviews.map((r, i) => (
              <div key={r.id} className={`review-card reveal reveal-d${Math.min(i+1,7)}`}>
                <div className="rev-author">
                  <div className="rev-avatar">
                    {r.avatar ? <img src={r.avatar} alt={r.author} /> : r.author.charAt(0).toUpperCase()}
                  </div>
                  <strong>{r.author}</strong>
                </div>
                <p>{r.text}</p>
                <span className="rev-date">{new Date(r.created_at).toLocaleDateString(lang === 'ru' ? 'ru-RU' : 'en-US')}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="cta-banner container">
        <div className="cta-inner reveal">
          <div className="cta-glow" />
          <h2>{t.ctaTitle}</h2>
          <p>{t.ctaSub}</p>
          <div className="cta-btns">
            <a href={BOT} target="_blank" rel="noreferrer" className="btn-primary btn-lg">{t.ctaBtn}</a>
            <a href={SUPPORT} target="_blank" rel="noreferrer" className="btn-ghost btn-lg">{t.ctaSupport}</a>
          </div>
        </div>
      </section>
    </div>
  );
}
