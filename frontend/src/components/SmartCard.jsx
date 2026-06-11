import { useState } from 'react';
import {
  Plane, CalendarDays, CheckCircle2, AlertTriangle, Mail,
  ExternalLink, X, ShieldAlert, Clock, Users,
  CreditCard, GitPullRequest, ClipboardList, Newspaper
} from 'lucide-react';
import {
  detectScenario,
  detectBrandColor,
  getBrandTheme,
  SCENARIO_DEFAULTS,
} from '../utils';
import './SmartCard.css';


/* ─── Helpers ────────────────────────────────────────────────────────────── */
function extractLinks(body = '') {
  const matches = body.match(/https?:\/\/[^\s"<>\]()]+/g) || [];
  return [...new Set(matches)].slice(0, 3);
}

function extractPNR(body = '') {
  const m = body.match(/\b([A-Z0-9]{6})\b/);
  return m ? m[1] : null;
}

function extractMeetingTime(body = '') {
  const m = body.match(/\b(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))\b/);
  return m ? m[1] : null;
}

function SafeLink({ url, label }) {
  const [confirmed, setConfirmed] = useState(false);
  if (!url) return null;
  const short = url.replace(/^https?:\/\/(www\.)?/, '').slice(0, 40);
  return (
    <div className="sc-safe-link">
      <ShieldAlert size={12} className="sc-safe-link-icon" />
      <span className="sc-safe-link-url">{short}{url.length > 43 ? '…' : ''}</span>
      {!confirmed ? (
        <button className="sc-safe-link-btn" onClick={() => setConfirmed(true)}>
          Verify & Open →
        </button>
      ) : (
        <a href={url} target="_blank" rel="noopener noreferrer" className="sc-safe-link-open">
          Open ↗
        </a>
      )}
    </div>
  );
}

function extractBankDetails(body = '') {
  const amountM = body.match(/Amount:\s*(\$[0-9,.]+)/i);
  const bankM = body.match(/Bank:\s*([^\n]+)/i);
  const accountM = body.match(/Account:\s*([^\n]+)/i);
  const routingM = body.match(/Routing:\s*([^\n]+)/i);
  return {
    amount: amountM ? amountM[1] : null,
    bank: bankM ? bankM[1].trim() : null,
    account: accountM ? accountM[1].trim() : null,
    routing: routingM ? routingM[1].trim() : null,
  };
}

/* ─── Card Templates ─────────────────────────────────────────────────────── */
function FlightCard({ email, onDismiss, onNavigate }) {
  const pnr = extractPNR(email.body || '');
  const links = extractLinks(email.body);
  const t = getBrandTheme(email, 'flight');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <Plane size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">FLIGHT / TRAVEL</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-chips">
          {pnr && (
            <span className="sc-chip" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
              PNR: {pnr}
            </span>
          )}
          <span className="sc-chip sc-chip--neutral">✈️ Booking</span>
        </div>
        {links.length > 0 && (
          <div className="sc-link-section">
            <span className="sc-link-label">⚠️ External link — verify before opening</span>
            <SafeLink url={links[0]} />
          </div>
        )}
      </div>
      <div className="sc-card-actions">
        <button className="sc-action-btn sc-action-btn--primary" onClick={onNavigate}>
          View Booking ➔
        </button>
      </div>
    </div>
  );
}

function MeetingCard({ email, onDismiss, onNavigate }) {
  const links = extractLinks(email.body);
  const time = extractMeetingTime(email.body);
  const t = getBrandTheme(email, 'meeting');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <CalendarDays size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">MEETING / EVENT</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-chips">
          {time && (
            <span className="sc-chip" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
              <Clock size={10} /> {time}
            </span>
          )}
          <span className="sc-chip sc-chip--neutral"><Users size={10} /> Invite</span>
        </div>
        {links.length > 0 && (
          <div className="sc-link-section">
            <span className="sc-link-label">⚠️ Join Link</span>
            <SafeLink url={links[0]} />
          </div>
        )}
      </div>
      <div className="sc-card-actions" style={{ flexDirection: 'row', gap: 6 }}>
        <button className="sc-action-btn" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
          Add to Calendar
        </button>
        <button className="sc-action-btn sc-action-btn--ghost" onClick={onNavigate}>
          View Event ➔
        </button>
      </div>
    </div>
  );
}

function GoodNewsCard({ email, onDismiss, onNavigate }) {
  const t = getBrandTheme(email, 'goodnews');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <CheckCircle2 size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">GOOD NEWS</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-body-text">{(email.body || '').slice(0, 100).trim()}…</div>
      </div>
      <div className="sc-card-actions" style={{ flexDirection: 'row', gap: 6 }}>
        <button className="sc-action-btn sc-action-btn--success" onClick={onDismiss}>
          Got it ✓
        </button>
        <button className="sc-action-btn sc-action-btn--ghost" onClick={onNavigate}>
          View Email ➔
        </button>
      </div>
    </div>
  );
}

function AlertCard({ email, onDismiss, onNavigate }) {
  const links = extractLinks(email.body);
  const t = getBrandTheme(email, 'alert');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <AlertTriangle size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">OFFICIAL NOTICE</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-body-text">{(email.body || '').slice(0, 80).trim()}…</div>
        {links.length > 0 && (
          <div className="sc-link-section">
            <span className="sc-link-label">⚠️ Verification Link</span>
            {links.slice(0, 1).map((l, i) => <SafeLink key={i} url={l} />)}
          </div>
        )}
      </div>
      <div className="sc-card-actions">
        <button className="sc-action-btn sc-action-btn--primary" onClick={onNavigate}>
          View Alert ➔
        </button>
      </div>
    </div>
  );
}

function FinanceCard({ email, onDismiss, onNavigate }) {
  const details = extractBankDetails(email.body || '');
  const links = extractLinks(email.body);
  const t = getBrandTheme(email, 'finance');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <CreditCard size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">FINANCE / INVOICE</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-chips">
          {details.amount && (
            <span className="sc-chip" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
              Amount: {details.amount}
            </span>
          )}
          {details.bank && <span className="sc-chip sc-chip--neutral">🏦 {details.bank}</span>}
        </div>
        {links.length > 0 && (
          <div className="sc-link-section">
            <span className="sc-link-label">⚠️ Invoice Link</span>
            <SafeLink url={links[0]} />
          </div>
        )}
      </div>
      <div className="sc-card-actions" style={{ flexDirection: 'row', gap: 6 }}>
        <button className="sc-action-btn sc-action-btn--primary" onClick={onNavigate}>
          Pay Invoice ➔
        </button>
      </div>
    </div>
  );
}

function CodeCard({ email, onDismiss, onNavigate }) {
  const links = extractLinks(email.body);
  const t = getBrandTheme(email, 'code');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <GitPullRequest size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">DEVELOPMENT / CODE</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-body-text">{(email.body || '').slice(0, 80)}...</div>
        {links.length > 0 && (
          <div className="sc-link-section">
            <span className="sc-link-label">⚠️ Repo Link</span>
            <SafeLink url={links[0]} />
          </div>
        )}
      </div>
      <div className="sc-card-actions">
        <button className="sc-action-btn sc-action-btn--primary" onClick={onNavigate}>
          Review PR ➔
        </button>
      </div>
    </div>
  );
}

function TaskCard({ email, onDismiss, onNavigate }) {
  const t = getBrandTheme(email, 'task');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <ClipboardList size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">TASK / TO-DO</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-body-text">{(email.body || '').slice(0, 80)}...</div>
      </div>
      <div className="sc-card-actions">
        <button className="sc-action-btn sc-action-btn--primary" onClick={onNavigate}>
          Complete Task ➔
        </button>
      </div>
    </div>
  );
}

function SpamCard({ email, onDismiss, onNavigate }) {
  const t = getBrandTheme(email, 'spam');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <ShieldAlert size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label" style={{ color: '#ef4444', fontWeight: 'bold' }}>⚠️ SYSTEM WARNING: SPAM</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-body-text">{(email.body || '').slice(0, 80)}...</div>
      </div>
      <div className="sc-card-actions">
        <button className="sc-action-btn sc-action-btn--primary" style={{ background: 'rgba(239,68,68,0.15)', color: '#ef4444', borderColor: 'rgba(239,68,68,0.3)' }} onClick={onDismiss}>
          Report & Delete ✕
        </button>
      </div>
    </div>
  );
}

function NewsletterCard({ email, onDismiss, onNavigate }) {
  const t = getBrandTheme(email, 'newsletter');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <Newspaper size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">NEWSLETTER / DIGEST</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-body-text">{(email.body || '').slice(0, 80)}...</div>
      </div>
      <div className="sc-card-actions">
        <button className="sc-action-btn sc-action-btn--primary" onClick={onNavigate}>
          Read Article ➔
        </button>
      </div>
    </div>
  );
}

function DefaultCard({ email, onDismiss, onNavigate }) {
  const t = getBrandTheme(email, 'default');
  return (
    <div className="sc-card" style={{ borderLeftColor: t.accent, background: t.bg }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <Mail size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">EMAIL</span>
          <span className="sc-card-sender">{email.sender?.split('@')[0]}</span>
        </div>
        <button className="sc-dismiss" onClick={onDismiss}><X size={13} /></button>
      </div>
      <div>
        <div className="sc-card-title">{email.subject}</div>
        <div className="sc-card-body-text">
          {(email.body || '').slice(0, 80).replace(/\n/g, ' ').trim()}...
        </div>
      </div>
      <div className="sc-card-actions">
        <button className="sc-action-btn sc-action-btn--primary" onClick={onNavigate}>
          View Email ➔
        </button>
      </div>
    </div>
  );
}

/* ─── Main SmartCard ─────────────────────────────────────────────────────── */
export function SmartCard({ email, onNavigate }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed || !email) return null;

  const scenario = detectScenario(email);
  const dismiss = () => setDismissed(true);

  switch (scenario) {
    case 'flight':     return <FlightCard     email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    case 'meeting':    return <MeetingCard    email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    case 'goodnews':   return <GoodNewsCard   email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    case 'finance':    return <FinanceCard    email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    case 'code':       return <CodeCard       email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    case 'task':       return <TaskCard       email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    case 'spam':       return <SpamCard       email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    case 'newsletter': return <NewsletterCard email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    case 'alert':      return <AlertCard      email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
    default:           return <DefaultCard    email={email} onDismiss={dismiss} onNavigate={onNavigate} />;
  }
}

/* ─── Rich Scenario Card (for EmailDetail/Reader) ────────────────────────── */
export function ScenarioStrip({ email }) {
  const [dismissed, setDismissed] = useState(false);
  if (!email) return null;
  const scenario = detectScenario(email);
  const t = getBrandTheme(email, scenario);

  const ICONS = {
    flight: Plane,
    meeting: CalendarDays,
    goodnews: CheckCircle2,
    alert: AlertTriangle,
    finance: CreditCard,
    code: GitPullRequest,
    task: ClipboardList,
    spam: ShieldAlert,
    newsletter: Newspaper,
    default: Mail,
  };

  const LABELS = {
    flight:     'Flight / Travel Details',
    meeting:    'Meeting / Event Invitation',
    goodnews:   'AI Insight: Good News Detected',
    alert:      'Official Notice / Action Required',
    finance:    'Payment Details / Invoice',
    code:       'Code Review / PR Request',
    task:       'Task Reminder / Action Required',
    spam:       '⚠️ Spam Detection Alert',
    newsletter: 'Newsletter / Weekly Digest',
    default:    null,
  };

  const label = LABELS[scenario];
  if (dismissed || !label || scenario === 'default') return null;

  const Icon = ICONS[scenario] || Mail;
  const links = extractLinks(email.body);
  const pnr = scenario === 'flight' ? extractPNR(email.body) : null;
  const time = scenario === 'meeting' ? extractMeetingTime(email.body) : null;
  const details = scenario === 'finance' ? extractBankDetails(email.body) : null;

  return (
    <div className="sc-card animate-slide-up" style={{ 
      borderLeftColor: t.accent, 
      background: t.bg, 
      borderColor: t.border,
      marginTop: '10px',
      marginBottom: '15px'
    }}>
      <div className="sc-card-header">
        <div className="sc-card-icon" style={{ background: `${t.accent}18`, color: t.accent }}>
          <Icon size={15} />
        </div>
        <div className="sc-card-meta">
          <span className="sc-card-label">{label}</span>
          <span className="sc-card-sender">Detected from: {email.sender}</span>
        </div>
        <button className="sc-dismiss" onClick={() => setDismissed(true)}><X size={13} /></button>
      </div>

      <div className="sc-card-chips" style={{ marginTop: '8px' }}>
        {pnr && (
          <span className="sc-chip" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
            PNR: {pnr}
          </span>
        )}
        {time && (
          <span className="sc-chip" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
            <Clock size={10} /> {time}
          </span>
        )}
        {details && details.amount && (
          <span className="sc-chip" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
            Amount: {details.amount}
          </span>
        )}
        {details && details.bank && (
          <span className="sc-chip sc-chip--neutral">🏦 {details.bank}</span>
        )}
        <span className="sc-chip sc-chip--neutral">✦ AI Insight</span>
      </div>

      {scenario === 'meeting' && (
        <div className="sc-card-actions" style={{ marginTop: '8px', marginBottom: '8px' }}>
          <button className="sc-action-btn" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
            <CalendarDays size={12} /> Add to Calendar
          </button>
        </div>
      )}

      {scenario === 'finance' && (
        <div className="sc-card-actions" style={{ marginTop: '8px', marginBottom: '8px' }}>
          <button className="sc-action-btn" style={{ color: t.accent, background: `${t.accent}14`, borderColor: `${t.accent}30` }}>
            Pay Invoice ➔
          </button>
        </div>
      )}

      {links.length > 0 && (
        <div className="sc-link-section" style={{ marginTop: '8px' }}>
          <span className="sc-link-label">⚠️ External link — verify before opening</span>
          {links.slice(0, 2).map((l, i) => <SafeLink key={i} url={l} />)}
        </div>
      )}
    </div>
  );
}

export default SmartCard;
