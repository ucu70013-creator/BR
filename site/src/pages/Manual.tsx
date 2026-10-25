import { useState } from 'react';
import { useLang } from '../App';
import { AccIcon } from '../components/Icons';

interface Method {
  icon: string;
  name: string;
  desc: string;
  cd: string;
  steps: string[];
  extra?: string;
  reasons?: string[];
  premium?: boolean;
}

const METHODS_RU: Method[] = [
  {
    icon: '🤖',
    name: 'Обычная Отправка (Ботнет)',
    desc: 'Массовая отправка жалоб на аккаунт/бот/канал через пул Telegram-аккаунтов. Жалобы отправляются пачками по 8 аккаунтов параллельно.',
    cd: '5 минут',
    steps: [
      'Нажать 🤖 Обычная Отправка',
      'Подтвердить мануал',
      'Ввести ссылку на цель: @username, t.me/username или https://t.me/username',
    ],
  },
  {
    icon: '👑',
    name: 'Премиальная Отправка',
    desc: 'То же самое что обычная, но через пул Premium-аккаунтов Telegram. В 2–3x выше доходимость жалоб.',
    cd: '30 минут',
    steps: [
      'Нажать 👑 Премиальная Отправка',
      'Подтвердить мануал',
      'Ввести ссылку на цель',
    ],
    extra: 'Эксклюзивный метод — доступен только с Премиум.',
    premium: true,
  },
  {
    icon: '🌐',
    name: 'Web',
    desc: 'Отправка жалоб через официальный сайт Telegram (веб-форма).',
    cd: '30 минут',
    steps: [
      'Нажать 🌐 Web',
      'Подтвердить мануал',
      'Ввести ссылку на цель',
    ],
  },
  {
    icon: '✉️',
    name: 'Mail',
    desc: 'Массовая рассылка email-жалоб на официальные почты Telegram через пул почтовых ящиков.',
    cd: '5 часов',
    steps: [
      'Нажать ✉️ Mail',
      'Ввести тему письма',
      'Ввести текст письма',
      'Ввести ссылку на цель',
    ],
    extra: 'Получатели: abuse@telegram.org, support@telegram.org и другие официальные адреса.',
  },
  {
    icon: '🤖',
    name: 'Бот',
    desc: 'Метод для сноса Telegram-ботов. Отправляет жалобы напрямую на бота.',
    cd: '5 мин (обычный) / 1 час (проверенный бот)',
    steps: [
      'Нажать 🤖 Бот',
      'Ввести @username бота (должен оканчиваться на bot)',
      'Выбрать причину жалобы',
    ],
    reasons: ['🔐 Персональные данные', '💊 Наркотики', '📝 Прочее'],
  },
  {
    icon: '📢',
    name: 'Канал',
    desc: 'Отправка жалоб на Telegram-канал или группу.',
    cd: '30 минут',
    steps: [
      'Нажать 📢 Канал',
      'Ввести ссылку на канал',
      'Выбрать причину',
    ],
    reasons: ['💊 Наркотики / незаконные товары', '🔐 Персональные данные', '🔞 Незаконный контент для взрослых', '📝 Прочее (свой текст)'],
  },
  {
    icon: '🇦🇺',
    name: 'AU Report',
    desc: 'Жалобы через специализированный сервис AU Report. Высокая эффективность.',
    cd: '1 час',
    steps: [
      'Нажать 🇦🇺 AU Report',
      'Подтвердить мануал',
      'Ввести ссылку на цель',
    ],
  },
  {
    icon: '🟣',
    name: 'TIDA',
    desc: 'Продвинутый метод жалоб с ИИ-генерацией текста. Поддерживает аккаунты, боты, чаты и каналы.',
    cd: '1 час',
    steps: [
      'Нажать 🟣 TIDA',
      'Выбрать тип цели (аккаунт / бот / чат / канал)',
      'Выбрать метод текста: 🤖 ИИ-анализ / 📝 Описать нарушение / ✏️ Свой текст',
      'Подтвердить или изменить сгенерированный текст',
    ],
  },
  {
    icon: '🇪🇺',
    name: 'DSA Report',
    desc: 'Жалобы через официальный европейский регулятор DSA (Digital Services Act). Эффективен против публичных каналов и ботов.',
    cd: '1 час',
    steps: [
      'Нажать 🇪🇺 DSA Report',
      'Ввести ссылку на цель',
      'Выбрать категорию нарушения',
      'Для некоторых категорий выбрать подкатегорию',
      'Подтвердить или изменить текст жалобы',
    ],
    reasons: ['Child abuse', 'Violence', 'Illegal goods', 'Illegal adult content', 'Personal data', 'Terrorism', 'Scam or spam', 'Other'],
  },
  {
    icon: '🌐',
    name: 'Universal метод',
    desc: 'Продвинутая универсальная атака — многовекторная отправка жалоб по нескольким каналам одновременно. Максимальное покрытие.',
    cd: '1 час',
    steps: [
      'Нажать 🌐 Universal метод',
      'Ввести ссылку на цель',
      'Подтвердить запуск',
    ],
    extra: 'Эксклюзивный метод — доступен только с Премиум.',
    premium: true,
  },
  {
    icon: '💀',
    name: 'Снос сессий',
    desc: 'Принудительный сброс всех активных сессий цели. Цель вылетает из всех устройств.',
    cd: '30 минут',
    steps: [
      'Нажать 💀 Снос сессий',
      'Ввести ссылку на аккаунт цели',
      'Подтвердить запуск',
    ],
    extra: 'Эксклюзивный метод — доступен только с Премиум.',
    premium: true,
  },
  {
    icon: '🌍',
    name: 'Домен киллер',
    desc: 'Блокировка доменов, связанных с целью. Отправляет жалобы регуляторам и хостинг-провайдерам.',
    cd: '1 час',
    steps: [
      'Нажать 🌍 Домен киллер',
      'Ввести домен цели',
      'Подтвердить запуск',
    ],
    extra: 'Эксклюзивный метод — доступен только с Премиум.',
    premium: true,
  },
  {
    icon: '📄',
    name: 'Telegraph снос',
    desc: 'Снос статей на Telegraph/Teletype через email-рассылку. ИИ автоматически читает статью и генерирует текст жалобы.',
    cd: '15 минут',
    steps: [
      'Нажать 📄 Telegraph снос',
      'Ввести ссылку на статью: https://telegra.ph/...',
      'ИИ читает содержимое и генерирует жалобу',
      'Подтвердить текст или написать свой',
    ],
    extra: 'Куда отправляется: abuse@telegram.org, support@telegram.org, dmca@telegram.org — 12 писем с 4 разных адресов. После отправки статья добавляется в мониторинг.',
  },
  {
    icon: '🏦',
    name: 'Блокировка карты',
    desc: 'Подача жалоб на банковские карты через официальные каналы.',
    cd: 'Нет',
    steps: [
      'Нажать 🏦 Блокировка карты',
      'Ввести номер карты',
    ],
  },
  {
    icon: '👤',
    name: 'Заказать удаление',
    desc: 'Ручная заявка на удаление аккаунта/канала/бота. Обрабатывается администрацией вручную.',
    cd: '—',
    steps: [
      'Нажать 👤 Заказать удаление',
      'Следовать инструкциям',
    ],
  },
  {
    icon: '🔗',
    name: 'Мониторинг',
    desc: 'Автоматическое отслеживание статуса цели после атаки. Бот проверяет цель каждые 10 минут и присылает уведомление когда цель снесена.',
    cd: '—',
    steps: [
      'Добавляется автоматически после атак',
      'Или вручную через меню мониторинга',
      'При сносе цели приходит уведомление 🔴',
    ],
    extra: 'Обычная подписка — 3 монитора (12 ч), Премиум — 5 мониторов (24 ч).',
  },
  {
    icon: '🪞',
    name: 'Зеркала',
    desc: 'Список рабочих зеркальных ботов Brown V2. Полный функционал — используй если основной недоступен.',
    cd: '—',
    steps: [
      'Создать бота через @BotFather',
      'Скопировать токен',
      'Нажать 🪞 Создать зеркало и вставить токен',
    ],
    extra: 'За создание 2 зеркал — +1 бесплатный репорт.',
  },
  {
    icon: '🎁',
    name: 'Промокод',
    desc: 'Активация промокода для получения подписки или бесплатных репортов.',
    cd: '—',
    steps: [
      'Нажать 🎁 Промокод',
      'Ввести код',
    ],
  },
  {
    icon: '🎡',
    name: 'Колесо репортов',
    desc: 'Бесплатный спин раз в 6 часов.',
    cd: '6 часов',
    steps: [
      'Нажать 🎡 Колесо репортов',
      'Крутить колесо',
    ],
    reasons: ['60% — Ничего', '19% — 1 репорт', '10% — 2 репорта', '5% — 3 репорта', '1% — 5 репортов 🍀'],
  },
  {
    icon: '🕵️',
    name: 'Пробив',
    desc: 'Поиск по открытым базам данных. Поддерживает 12 типов запросов: телефон, ФИО, email, никнейм, пароль, СНИЛС, ИНН, авто, IP, ВКонтакте, TikTok и адрес.',
    cd: '30 секунд',
    steps: [
      'Нажать 🕵️ Пробив в меню',
      'Ввести запрос в нужном формате (примеры показаны в боте)',
    ],
    reasons: [
      '👤 ФИО: Иванов Иван Иванович',
      '👤 ФИО + дата: Иванов Иван 15.03.1985 Москва',
      '📱 Телефон: 79277231370',
      '📧 Email: user@gmail.com',
      '🔑 Никнейм: nick:username123',
      '🔐 Пароль: pass:qwerty123',
      '🪪 СНИЛС: snils12345678901',
      '🏦 ИНН: inn582801503237',
      '🚗 Авто (ГРЗ): А123ВС77 или VIN',
      '🌐 IP: 8.8.8.8',
      '💙 ВКонтакте: vkid123456789',
      '🎵 TikTok: tt:username',
      '🏠 Адрес: addr:Москва, ул. Ленина 1',
    ],
    extra: 'Обычная подписка — 5 запросов в час. Премиум — без ограничений. КД 30 сек между запросами.',
  },
];

const METHODS_EN: Method[] = [
  {
    icon: '🤖',
    name: 'Regular Send (Botnet)',
    desc: 'Mass reporting on an account/bot/channel via a pool of Telegram accounts. Reports are sent in batches of 8 accounts in parallel.',
    cd: '5 minutes',
    steps: [
      'Tap 🤖 Regular Send',
      'Confirm the manual',
      'Enter the target link: @username, t.me/username or https://t.me/username',
    ],
  },
  {
    icon: '👑',
    name: 'Premium Send',
    desc: 'Same as regular, but through a pool of Telegram Premium accounts. 2–3x higher report delivery rate.',
    cd: '30 minutes',
    steps: [
      'Tap 👑 Premium Send',
      'Confirm the manual',
      'Enter the target link',
    ],
    extra: 'Exclusive method — available with Premium only.',
    premium: true,
  },
  {
    icon: '🌐',
    name: 'Web',
    desc: "Reports via Telegram's official website (web form).",
    cd: '30 minutes',
    steps: ['Tap 🌐 Web', 'Confirm the manual', 'Enter the target link'],
  },
  {
    icon: '✉️',
    name: 'Mail',
    desc: 'Mass email complaints to official Telegram addresses via a pool of mailboxes.',
    cd: '5 hours',
    steps: ['Tap ✉️ Mail', 'Enter email subject', 'Enter email body', 'Enter the target link'],
    extra: 'Recipients: abuse@telegram.org, support@telegram.org and other official addresses.',
  },
  {
    icon: '🤖',
    name: 'Bot',
    desc: 'Method for taking down Telegram bots. Sends reports directly at the bot.',
    cd: '5 min (regular) / 1 hour (verified bot)',
    steps: ['Tap 🤖 Bot', 'Enter @username of the bot (must end with "bot")', 'Choose report reason'],
    reasons: ['🔐 Personal data', '💊 Drugs', '📝 Other'],
  },
  {
    icon: '📢',
    name: 'Channel',
    desc: 'Reports against a Telegram channel or group.',
    cd: '30 minutes',
    steps: ['Tap 📢 Channel', 'Enter channel link', 'Select reason'],
    reasons: ['💊 Drugs / illegal goods', '🔐 Personal data', '🔞 Illegal adult content', '📝 Other (custom text)'],
  },
  {
    icon: '🇦🇺',
    name: 'AU Report',
    desc: 'Reports via the specialized AU Report service. High effectiveness.',
    cd: '1 hour',
    steps: ['Tap 🇦🇺 AU Report', 'Confirm the manual', 'Enter the target link'],
  },
  {
    icon: '🟣',
    name: 'TIDA',
    desc: 'Advanced reporting with AI-generated text. Supports accounts, bots, chats and channels.',
    cd: '1 hour',
    steps: ['Tap 🟣 TIDA', 'Choose target type (account / bot / chat / channel)', 'Choose text method: 🤖 AI analysis / 📝 Describe violation / ✏️ Custom text', 'Confirm or edit the generated text'],
  },
  {
    icon: '🇪🇺',
    name: 'DSA Report',
    desc: 'Reports via the EU official DSA (Digital Services Act) regulator. Effective against public channels and bots.',
    cd: '1 hour',
    steps: ['Tap 🇪🇺 DSA Report', 'Enter target link', 'Select violation category', 'Select subcategory if applicable', 'Confirm or edit the complaint text'],
    reasons: ['Child abuse', 'Violence', 'Illegal goods', 'Illegal adult content', 'Personal data', 'Terrorism', 'Scam or spam', 'Other'],
  },
  {
    icon: '🌐',
    name: 'Universal Method',
    desc: 'Advanced multi-vector attack — reports sent across multiple channels simultaneously for maximum coverage.',
    cd: '1 hour',
    steps: [
      'Tap 🌐 Universal Method',
      'Enter the target link',
      'Confirm launch',
    ],
    extra: 'Exclusive method — available with Premium only.',
    premium: true,
  },
  {
    icon: '💀',
    name: 'Session Knockdown',
    desc: 'Force-logout all active sessions of the target. The target gets signed out from every device.',
    cd: '30 minutes',
    steps: [
      'Tap 💀 Session Knockdown',
      'Enter the target account link',
      'Confirm launch',
    ],
    extra: 'Exclusive method — available with Premium only.',
    premium: true,
  },
  {
    icon: '🌍',
    name: 'Domain Killer',
    desc: "Block domains linked to the target. Files complaints with regulators and hosting providers.",
    cd: '1 hour',
    steps: [
      'Tap 🌍 Domain Killer',
      'Enter the target domain',
      'Confirm launch',
    ],
    extra: 'Exclusive method — available with Premium only.',
    premium: true,
  },
  {
    icon: '📄',
    name: 'Telegraph Takedown',
    desc: 'Takedown of Telegraph/Teletype articles via email complaints. AI automatically reads the article and generates complaint text.',
    cd: '15 minutes',
    steps: ['Tap 📄 Telegraph Takedown', 'Enter article link: https://telegra.ph/...', 'AI reads the article and generates the complaint', 'Confirm or write your own text'],
    extra: 'Sent to: abuse@telegram.org, support@telegram.org, dmca@telegram.org — 12 emails from 4 addresses. Article is added to monitoring after submission.',
  },
  {
    icon: '🏦',
    name: 'Card Block',
    desc: 'File complaints about bank cards through official channels.',
    cd: 'None',
    steps: ['Tap 🏦 Card Block', 'Enter card number'],
  },
  {
    icon: '👤',
    name: 'Order Removal',
    desc: 'Manual removal request for an account/channel/bot. Processed by admins.',
    cd: '—',
    steps: ['Tap 👤 Order Removal', 'Follow the instructions'],
  },
  {
    icon: '🔗',
    name: 'Monitoring',
    desc: 'Automatic status tracking of a target after an attack. Bot checks every 10 minutes and notifies when the target is taken down.',
    cd: '—',
    steps: ['Added automatically after attacks', 'Or manually through the monitoring menu', 'Get notified 🔴 when target is down'],
    extra: 'Regular subscription — 3 monitors (12 h), Premium — 5 monitors (24 h).',
  },
  {
    icon: '🪞',
    name: 'Mirrors',
    desc: 'List of working Brown V2 mirror bots. Full functionality — use if the main bot is unavailable.',
    cd: '—',
    steps: ['Create a bot via @BotFather', 'Copy the token', 'Tap 🪞 Create Mirror and paste the token'],
    extra: 'Creating 2 mirrors earns +1 free report.',
  },
  {
    icon: '🎁',
    name: 'Promo Code',
    desc: 'Activate a promo code to get a subscription or free reports.',
    cd: '—',
    steps: ['Tap 🎁 Promo Code', 'Enter the code'],
  },
  {
    icon: '🎡',
    name: 'Report Wheel',
    desc: 'Free spin every 6 hours.',
    cd: '6 hours',
    steps: ['Tap 🎡 Report Wheel', 'Spin the wheel'],
    reasons: ['60% — Nothing', '19% — 1 report', '10% — 2 reports', '5% — 3 reports', '1% — 5 reports 🍀'],
  },
  {
    icon: '🕵️',
    name: 'Lookup (Probiv)',
    desc: 'Search across open databases. Supports 12 query types: phone, full name, email, username, password, SNILS, INN, vehicle, IP, VKontakte, TikTok and address.',
    cd: '30 seconds',
    steps: [
      'Tap 🕵️ Lookup in the menu',
      'Enter your query in the supported format (examples shown in the bot)',
    ],
    reasons: [
      '👤 Full name: Ivanov Ivan Ivanovich',
      '👤 Name + date: Ivanov Ivan 15.03.1985 Moscow',
      '📱 Phone: 79277231370',
      '📧 Email: user@gmail.com',
      '🔑 Username: nick:username123',
      '🔐 Password: pass:qwerty123',
      '🪪 SNILS: snils12345678901',
      '🏦 INN: inn582801503237',
      '🚗 Vehicle plate: A123BC77 or VIN',
      '🌐 IP: 8.8.8.8',
      '💙 VKontakte: vkid123456789',
      '🎵 TikTok: tt:username',
      '🏠 Address: addr:Moscow, Lenin St 1',
    ],
    extra: 'Regular subscription — 5 queries per hour. Premium — unlimited. 30 sec cooldown between queries.',
  },
];

export default function Manual() {
  const { lang } = useLang();
  const [open, setOpen] = useState<number | null>(null);
  const methods = lang === 'ru' ? METHODS_RU : METHODS_EN;

  return (
    <div className="page-inner container">
      <div className="page-head">
        <div className="sec-label">МАНУАЛ</div>
        <h1>{lang === 'ru' ? 'Мануал — Brown V2' : 'Manual — Brown V2'}</h1>
        <p>{lang === 'ru' ? 'Подробное описание всех методов бота' : 'Detailed description of all bot methods'}</p>
      </div>

      <div className="accordion">
        {methods.map((m, i) => (
          <div key={i} className={`acc-item${open === i ? ' open' : ''}`}>
            <button className="acc-head" onClick={() => setOpen(open === i ? null : i)}>
              <span className="acc-icon"><AccIcon emoji={m.icon} /></span>
              <span className="acc-name">
                {m.name}
                {m.premium && <span className="badge-premium">PREMIUM</span>}
              </span>
              <span className="acc-cd">{lang === 'ru' ? 'КД' : 'CD'}: {m.cd}</span>
              <svg className="acc-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6"/></svg>
            </button>
            {open === i && (
              <div className="acc-body">
                <p className="acc-desc">{m.desc}</p>
                <div className="acc-section">
                  <strong>{lang === 'ru' ? '📋 Как использовать:' : '📋 How to use:'}</strong>
                  <ol>
                    {m.steps.map((s, si) => <li key={si}>{s}</li>)}
                  </ol>
                </div>
                {m.reasons && (
                  <div className="acc-section">
                    <strong>{lang === 'ru' ? '📌 Причины / Варианты:' : '📌 Reasons / Options:'}</strong>
                    <ul>
                      {m.reasons.map((r, ri) => <li key={ri}>{r}</li>)}
                    </ul>
                  </div>
                )}
                {m.extra && (
                  <div className="acc-extra">{m.extra}</div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
