import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, CheckCircle2, Copy, ExternalLink, MessageCircle, Power, QrCode, RefreshCw, Send, ShieldCheck } from 'lucide-react';
import { api, type TelegramChatCandidate, type TelegramSetupInfo, type TelegramStatus } from '@shared/api/client';

export function TelegramDashboardPage() {
  const [setup, setSetup] = useState<TelegramSetupInfo | null>(null);
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [chats, setChats] = useState<TelegramChatCandidate[]>([]);
  const [token, setToken] = useState('');
  const [manualChatId, setManualChatId] = useState('');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [nextSetup, nextStatus] = await Promise.all([api.telegramSetup(), api.telegramStatus()]);
      setSetup(nextSetup);
      setStatus(nextStatus);
      setManualChatId(nextSetup.allowed_chat_ids[0] ?? '');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Telegram-Status konnte nicht geladen werden.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const qrUrl = useMemo(() => {
    const payload = setup?.qr_payload || setup?.bot_url || '';
    return payload ? `https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=10&data=${encodeURIComponent(payload)}` : '';
  }, [setup]);

  async function saveToken() {
    if (!token.trim()) return;
    await run('save-token', async () => {
      await api.updateTelegramSettings({ bot_token: token.trim() });
      setToken('');
      setNotice('Telegram Bot Token wurde gespeichert.');
      await load();
    });
  }

  async function saveChatId(chatId = manualChatId) {
    const clean = chatId.trim();
    if (!clean) return;
    await run('save-chat', async () => {
      await api.updateTelegramSettings({ allowed_chat_ids: [clean], default_chat_id: clean });
      setNotice(`Chat-ID ${clean} wurde freigeschaltet.`);
      await load();
    });
  }

  async function discoverChats() {
    await run('discover', async () => {
      const result = await api.telegramDiscoverChats();
      setChats(result.chats);
      setNotice(result.chats.length ? 'Chats geladen.' : 'Noch kein Chat gefunden. Schreibe dem Bot zuerst eine Nachricht.');
    });
  }

  async function toggleEnabled() {
    await run('toggle', async () => {
      if (status?.enabled) {
        await api.disableTelegramAgent();
        setNotice('Telegram Chat wurde deaktiviert.');
      } else {
        await api.enableTelegramAgent();
        setNotice('Telegram Chat wurde aktiviert.');
      }
      await load();
    });
  }

  async function sendTest() {
    await run('test', async () => {
      await api.testTelegramAgent('Roboter Steve Telegram ist verbunden.');
      setNotice('Testnachricht wurde gesendet.');
      await load();
    });
  }

  async function copyLink() {
    const link = setup?.bot_url || '';
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setNotice('Telegram-Link kopiert.');
    } catch {
      setError('Telegram-Link konnte nicht kopiert werden.');
    }
  }

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError('');
    setNotice('');
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Telegram-Aktion fehlgeschlagen.');
    } finally {
      setBusy('');
    }
  }

  const readyForPairing = Boolean(setup?.bot_token_configured && (setup?.allowed_chat_count || setup?.auto_pair_first_chat));
  const configured = Boolean(setup?.configured);
  const tokenConfigured = Boolean(setup?.bot_token_configured);
  const chatConfigured = Boolean(setup?.allowed_chat_count);

  return (
    <div className="page-stack telegram-page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Telegram Chat</span>
          <h1>Roboter Steve Chatbot</h1>
          <p>Bot verbinden, Chat per QR-Code öffnen und den Telegram-Agenten aktivieren.</p>
        </div>
        <div className="page-actions">
          <button className="button secondary" type="button" onClick={() => void load()} disabled={Boolean(busy)}>
            <RefreshCw size={18} /> Aktualisieren
          </button>
          <button className={status?.enabled ? 'button secondary' : 'button primary'} type="button" onClick={() => void toggleEnabled()} disabled={Boolean(busy) || !setup?.bot_token_configured}>
            {busy === 'toggle' ? <Activity size={18} /> : <Power size={18} />} {status?.enabled ? 'Deaktivieren' : 'Aktivieren'}
          </button>
        </div>
      </header>

      {error && <section className="panel error-panel">{error}</section>}
      {notice && <section className="panel success-panel">{notice}</section>}

      <section className="telegram-setup-grid">
        <article className="panel telegram-qr-panel">
          <div className="telegram-qr-frame">
            {qrUrl ? <img src={qrUrl} alt="Telegram QR-Code fuer Roboter Steve" /> : <QrCode size={96} />}
          </div>
          <div className="telegram-qr-copy">
            <span className="eyebrow">QR-Code</span>
            <h2>{setup?.bot?.username ? `@${setup.bot.username}` : 'Bot noch nicht erkannt'}</h2>
            <p>{setup?.bot_url ? 'Mit dem Handy scannen oder Link öffnen, dann dem Bot eine Nachricht schreiben.' : 'Trage zuerst den BotFather Token ein.'}</p>
            <div className="telegram-actions-row">
              <button className="button secondary" type="button" onClick={() => void copyLink()} disabled={!setup?.bot_url}>
                <Copy size={18} /> Link kopieren
              </button>
              {setup?.bot_url && (
                <a className="button" href={setup.bot_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={18} /> Öffnen
                </a>
              )}
            </div>
          </div>
        </article>

        <article className="panel telegram-status-panel">
          <StatusItem icon={<ShieldCheck size={18} />} label="Bot Token" value={tokenConfigured ? 'gesetzt' : 'fehlt'} ok={tokenConfigured} />
          <StatusItem icon={<MessageCircle size={18} />} label="Chat-ID" value={chatConfigured ? `${setup?.allowed_chat_count} erlaubt` : 'fehlt'} ok={chatConfigured} />
          <StatusItem icon={<Power size={18} />} label="Agent" value={status?.enabled ? 'aktiviert' : 'deaktiviert'} ok={Boolean(status?.enabled)} />
          <StatusItem icon={<CheckCircle2 size={18} />} label="Pairing" value={readyForPairing ? 'bereit' : 'nicht bereit'} ok={readyForPairing} />
        </article>
      </section>

      <section className="telegram-settings-grid">
        <article className="panel telegram-form-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">1. Bot Token</span>
              <h2>Token eintragen</h2>
            </div>
          </div>
          <p>Den Token bekommst du in Telegram bei BotFather mit <code>/newbot</code>. Du kannst ihn hier speichern oder in <code>agent-api/.env</code> als <code>TELEGRAM_BOT_TOKEN</code> setzen.</p>
          <label className="telegram-field">
            Bot Token
            <input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder={tokenConfigured ? 'Token ist gespeichert' : '123456:ABC...'} />
          </label>
          <button className="button primary" type="button" onClick={() => void saveToken()} disabled={Boolean(busy) || !token.trim()}>
            {busy === 'save-token' ? <Activity size={18} /> : <CheckCircle2 size={18} />} Token speichern
          </button>
        </article>

        <article className="panel telegram-form-panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">2. Chat koppeln</span>
              <h2>Chat-ID freigeben</h2>
            </div>
          </div>
          <p>Nach dem Scannen schreibe dem Bot eine Nachricht. Wenn noch keine Chat-ID hinterlegt ist, wird dieser erste Chat automatisch freigeschaltet.</p>
          <div className="telegram-actions-row">
            <button className="button secondary" type="button" onClick={() => void discoverChats()} disabled={Boolean(busy) || !tokenConfigured}>
              {busy === 'discover' ? <Activity size={18} /> : <RefreshCw size={18} />} Chats suchen
            </button>
            <button className="button secondary" type="button" onClick={() => void sendTest()} disabled={Boolean(busy) || !configured}>
              {busy === 'test' ? <Activity size={18} /> : <Send size={18} />} Test senden
            </button>
          </div>
          <label className="telegram-field">
            Erlaubte Chat-ID
            <input value={manualChatId} onChange={(event) => setManualChatId(event.target.value)} placeholder="z. B. 6516768203" />
          </label>
          <button className="button primary" type="button" onClick={() => void saveChatId()} disabled={Boolean(busy) || !manualChatId.trim()}>
            <ShieldCheck size={18} /> Chat-ID speichern
          </button>
        </article>
      </section>

      {chats.length > 0 && (
        <section className="panel telegram-chat-list">
          <div className="section-title">
            <div>
              <span className="eyebrow">Gefundene Chats</span>
              <h2>Telegram Updates</h2>
            </div>
          </div>
          {chats.map((chat) => (
            <div className="telegram-chat-row" key={chat.chat_id}>
              <div>
                <strong>{chat.first_name || chat.username || chat.title || chat.chat_id}</strong>
                <span>{chat.chat_id} · {chat.authorized ? 'freigeschaltet' : 'nicht freigeschaltet'}</span>
              </div>
              <button className="button secondary" type="button" onClick={() => void saveChatId(chat.chat_id)} disabled={Boolean(busy)}>
                Übernehmen
              </button>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function StatusItem({ icon, label, value, ok }: { icon: ReactNode; label: string; value: string; ok: boolean }) {
  return (
    <div className={`telegram-status-item ${ok ? 'ok' : ''}`}>
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
    </div>
  );
}
