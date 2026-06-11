import { useState, useEffect, useCallback } from 'react';
import {
  Mail, Calendar, Users, HardDrive, User, Layers,
  MessageSquare, RefreshCw, Send, Plus, ChevronRight,
  Paperclip, Clock, CheckCircle2, AlertCircle, Wifi,
  WifiOff, MoreHorizontal, Search, X, Loader2, Sparkles,
  Tag, FileText, Zap, CalendarPlus, Plane, AlertTriangle,
  CreditCard, GitPullRequest, ClipboardList, ShieldAlert, Newspaper
} from 'lucide-react';
import { ScenarioStrip } from '../components/SmartCard';
import { detectScenario } from '../utils';
import './OutlookPage.css';

const API = '/api/graph';

async function gfetch(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

const TABS = [
  { id: 'mail',     label: 'Mail',      icon: Mail },
  { id: 'calendar', label: 'Calendar',  icon: Calendar },
  { id: 'contacts', label: 'Contacts',  icon: Users },
  { id: 'profile',  label: 'Profile',   icon: User },
  { id: 'teams',    label: 'Teams',     icon: MessageSquare },
];

/* ─── small helpers ─────────────────────────────────────────────────────── */
function Avatar({ name = '?', size = 36, color }) {
  const colors = ['#6366f1','#f97316','#10b981','#f43f5e','#a78bfa','#fbbf24','#06b6d4'];
  const bg = color || colors[(name.charCodeAt(0) || 0) % colors.length];
  return (
    <div className="ol-avatar" style={{ width: size, height: size, background: bg, fontSize: size * 0.38 }}>
      {name.charAt(0).toUpperCase()}
    </div>
  );
}

function EmailAvatar({ email, size = 34 }) {
  const scenario = detectScenario(email);
  const colors = {
    flight:     { bg: 'rgba(14, 165, 233, 0.12)', fg: '#0ea5e9' },
    meeting:    { bg: 'rgba(167, 139, 250, 0.12)', fg: '#a78bfa' },
    goodnews:   { bg: 'rgba(16, 185, 129, 0.12)', fg: '#10b981' },
    alert:      { bg: 'rgba(245, 158, 11, 0.12)',  fg: '#f59e0b' },
    finance:    { bg: 'rgba(16, 185, 129, 0.12)',  fg: '#10b981' },
    code:       { bg: 'rgba(129, 140, 248, 0.12)', fg: '#818cf8' },
    task:       { bg: 'rgba(244, 63, 94, 0.12)',   fg: '#f43f5e' },
    spam:       { bg: 'rgba(239, 68, 68, 0.12)',   fg: '#ef4444' },
    newsletter: { bg: 'rgba(6, 182, 212, 0.12)',   fg: '#06b6d4' },
    default:    { bg: 'rgba(99, 102, 241, 0.12)',  fg: '#6366f1' },
  };

  const config = colors[scenario] || colors.default;

  const Icon = {
    flight: Plane,
    meeting: Calendar,
    goodnews: CheckCircle2,
    alert: AlertTriangle,
    finance: CreditCard,
    code: GitPullRequest,
    task: ClipboardList,
    spam: ShieldAlert,
    newsletter: Newspaper,
    default: Mail,
  }[scenario] || Mail;

  return (
    <div 
      className="ol-avatar ol-avatar-icon" 
      style={{ 
        background: config.bg, 
        color: config.fg, 
        width: size, 
        height: size, 
        borderRadius: '50%', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center', 
        flexShrink: 0 
      }}
    >
      <Icon size={size * 0.45} />
    </div>
  );
}

function StatusBadge({ mode }) {
  const live = mode === 'live';
  return (
    <span className={`ol-status-badge ${live ? 'ol-status-live' : 'ol-status-mock'}`}>
      {live ? <Wifi size={10} /> : <WifiOff size={10} />}
      {live ? 'Live · Microsoft Graph' : 'Mock Mode'}
    </span>
  );
}

function SectionLoader() {
  return (
    <div className="ol-loader">
      <Loader2 size={22} className="ol-spin" />
      <span>Loading…</span>
    </div>
  );
}

function ErrorCard({ msg, onRetry }) {
  return (
    <div className="ol-error-card">
      <AlertCircle size={18} />
      <span>{msg}</span>
      {onRetry && <button className="btn btn-secondary" onClick={onRetry}>Retry</button>}
    </div>
  );
}

/* ─── Mail Tab ───────────────────────────────────────────────────────────── */
function MailTab() {
  const [messages, setMessages] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [composing, setComposing] = useState(false);
  const [form, setForm] = useState({ to: '', subject: '', body: '' });
  const [replyToId, setReplyToId] = useState(null);
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState(null);

  // AI state
  const [aiClassification, setAiClassification] = useState(null);
  const [aiSummary, setAiSummary]               = useState(null);
  const [aiDraft, setAiDraft]                   = useState(null);
  const [aiCalEvent, setAiCalEvent]             = useState(null); // add-to-calendar result
  const [aiLoading, setAiLoading]               = useState(null); // 'classify'|'summarize'|'draft'|'calendar'
  const [aiError, setAiError]                   = useState(null);
  const [draftQuality, setDraftQuality]         = useState('balanced');

  const [bulkClassifications, setBulkClassifications] = useState({});
  const [classifyingAll, setClassifyingAll] = useState(false);

  // Thread and user state
  const [threadMessages, setThreadMessages]     = useState([]);
  const [loadingThread, setLoadingThread]       = useState(false);
  const [currentUser, setCurrentUser]           = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await gfetch('/mail/inbox?top=50');
      setMessages(d.messages || []);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Fetch current user details on mount
  useEffect(() => {
    gfetch('/users/me')
      .then(setCurrentUser)
      .catch(() => {});
  }, []);

  // Fetch thread messages when selected message changes
  useEffect(() => {
    if (!selected) {
      setThreadMessages([]);
      return;
    }
    if (!selected.thread_id) {
      setThreadMessages([selected]);
      return;
    }
    let active = true;
    const fetchThread = async () => {
      setLoadingThread(true);
      try {
        const d = await gfetch(`/mail/thread/${selected.thread_id}`);
        if (active) {
          if (d.messages && d.messages.length > 0) {
            setThreadMessages(d.messages);
          } else {
            setThreadMessages([selected]);
          }
        }
      } catch (e) {
        console.error('Failed to fetch thread:', e);
        if (active) setThreadMessages([selected]);
      } finally {
        if (active) setLoadingThread(false);
      }
    };
    fetchThread();
    return () => { active = false; };
  }, [selected?.thread_id, selected?.id]);

  // Auto-refresh inbox every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      gfetch('/mail/inbox?top=50')
        .then(d => setMessages(d.messages || []))
        .catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Reset AI panel when a new message is selected
  useEffect(() => {
    setAiClassification(null);
    setAiSummary(null);
    setAiDraft(null);
    setAiCalEvent(null);
    setAiError(null);
  }, [selected?.id]);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleClassifyAll = async () => {
    if (messages.length === 0) return;
    setClassifyingAll(true);
    const newClassifications = { ...bulkClassifications };
    for (const m of messages) {
      if (newClassifications[m.id]) continue;
      try {
        const d = await gfetch('/mail/classify', { method: 'POST', body: JSON.stringify({ message_id: m.id }) });
        if (d.classification) {
          newClassifications[m.id] = d.classification;
          setBulkClassifications({ ...newClassifications });
        }
      } catch (e) {
        console.error(e);
      }
    }
    setClassifyingAll(false);
  };

  const runAI = async (action) => {
    if (!selected?.id) return;
    setAiLoading(action); setAiError(null);
    try {
      if (action === 'classify') {
        const d = await gfetch('/mail/classify', { method: 'POST', body: JSON.stringify({ message_id: selected.id }) });
        setAiClassification(d.classification);
      } else if (action === 'summarize') {
        const d = await gfetch('/mail/summarize', { method: 'POST', body: JSON.stringify({ message_id: selected.id }) });
        setAiSummary(d.summary);
      } else if (action === 'draft') {
        const d = await gfetch('/mail/draft-reply', { method: 'POST', body: JSON.stringify({ message_id: selected.id, quality: draftQuality }) });
        setAiDraft(d.draft);
        setForm(f => ({ ...f, to: selected.sender, subject: `Re: ${selected.subject}`, body: d.draft }));
        setReplyToId(selected.id);
        setComposing(true);
      } else if (action === 'calendar') {
        const d = await gfetch('/mail/add-to-calendar', { method: 'POST', body: JSON.stringify({ message_id: selected.id }) });
        if (d.status === 'created') {
          setAiCalEvent(d);
          showToast('Event added to your calendar!');
        } else {
          setAiError(d.message || 'No meeting details found in this email');
        }
      }
    } catch (e) { setAiError(e.message); }
    finally { setAiLoading(null); }
  };

  const PRIORITY_COLORS = { critical: '#f43f5e', high: '#f97316', normal: '#10b981', low: '#6366f1' };

  const handleSend = async () => {
    if (!form.to || !form.subject) return;
    setSending(true);
    const sentSubject = form.subject;
    const sentBody = form.body;
    const sentTo = form.to;
    try {
      await gfetch('/mail/send', {
        method: 'POST',
        body: JSON.stringify({ to: sentTo, subject: sentSubject, body: sentBody, reply_to_id: replyToId }),
      });
      showToast('Email sent successfully!');
      setComposing(false);
      setForm({ to: '', subject: '', body: '' });
      setReplyToId(null);

      // Run AI scheduling on the sent email content
      try {
        const calResult = await gfetch('/calendar/create-from-text', {
          method: 'POST',
          body: JSON.stringify({ subject: sentSubject, body: sentBody, recipient: sentTo })
        });
        if (calResult.status === 'created') {
          showToast(`\ud83d\udcc5 Auto-scheduled: "${calResult.title}" on ${new Date(calResult.start).toLocaleDateString()}`, 'success');
        }
      } catch (e) {
        console.error('Failed to auto-schedule meeting from sent mail:', e);
      }
    } catch (e) { showToast(e.message, 'error'); }
    finally { setSending(false); }
  };

  return (
    <div className="ol-mail-layout">
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}

      {/* Left: message list */}
      <div className="ol-mail-list glass-card">
        <div className="ol-mail-list-header">
          <span className="ol-section-title"><Mail size={14}/> Inbox</span>
          <div className="ol-mail-list-actions">
            <button className="btn btn-secondary" onClick={handleClassifyAll} disabled={classifyingAll} title="Classify All">
              {classifyingAll ? <Loader2 size={13} className="ol-spin"/> : <Sparkles size={13}/>} Classify All
            </button>
            <button className="btn btn-primary" onClick={() => { setReplyToId(null); setComposing(true); }} id="outlook-compose-btn">
              <Plus size={13}/> Compose
            </button>
            <button className="btn-icon" onClick={load} title="Refresh"><RefreshCw size={14}/></button>
          </div>
        </div>
        
        <div className="ol-mail-list-content">
          {loading && <SectionLoader />}
          {error && <ErrorCard msg={error} onRetry={load} />}
          {!loading && !error && messages.length === 0 && (
            <div className="empty-state"><Mail size={40}/><p className="empty-state-title">No messages</p></div>
          )}
          {messages.map(m => (
            <div
              key={m.id}
              className={`ol-mail-item ${!m.is_read ? 'ol-unread' : ''} ${selected?.id === m.id ? 'ol-selected' : ''}`}
              onClick={() => setSelected(m)}
            >
              <EmailAvatar email={m} size={34} />
              <div className="ol-mail-item-body">
                <div className="ol-mail-item-from">{(m.sender || '').split('@')[0]}</div>
                <div className="ol-mail-item-subject">{m.subject}</div>
                {bulkClassifications[m.id] ? (
                  <div style={{ marginTop: 4, display: 'flex', gap: 4 }}>
                    <span className="ol-ai-chip" style={{ fontSize: 10, padding: '2px 6px', background: PRIORITY_COLORS[bulkClassifications[m.id].priority] || '#6366f1' }}>
                      {bulkClassifications[m.id].priority?.toUpperCase()}
                    </span>
                    <span className="ol-ai-chip ol-ai-chip-cat" style={{ fontSize: 10, padding: '2px 6px' }}>
                      {bulkClassifications[m.id].category}
                    </span>
                  </div>
                ) : (
                  <div className="ol-mail-item-preview">{(m.snippet || m.body || '').slice(0, 80)}</div>
                )}
              </div>
              <div className="ol-mail-item-meta">
                {m.timestamp && (
                  <span className="ol-mail-item-time">
                    {new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
                {!m.is_read && <span className="ol-unread-dot"/>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Right: message detail or compose */}
      <div className="ol-mail-detail glass-card">
        {composing ? (
          <div className="ol-compose">
            <div className="ol-compose-header">
              <span className="ol-section-title"><Send size={14}/> New Message</span>
              <button className="btn-icon" onClick={() => setComposing(false)}><X size={14}/></button>
            </div>
            <input className="input" placeholder="To (email address)" value={form.to}
              onChange={e => setForm(f => ({ ...f, to: e.target.value }))} />
            <input className="input" placeholder="Subject" value={form.subject}
              onChange={e => setForm(f => ({ ...f, subject: e.target.value }))} />
            <textarea className="input" rows={10} placeholder="Message body…" value={form.body}
              onChange={e => setForm(f => ({ ...f, body: e.target.value }))} />
            <button className="btn btn-primary" onClick={handleSend} disabled={sending} id="outlook-send-btn">
              {sending ? <Loader2 size={13} className="ol-spin"/> : <Send size={13}/>}
              {sending ? 'Sending…' : 'Send Email'}
            </button>
          </div>
        ) : selected ? (
          <div className="ol-mail-reader">
            <h2 className="ol-mail-subject">{selected.subject}</h2>
            <ScenarioStrip email={selected} />
            <div className="ol-mail-from-row">
              <Avatar name={selected.sender || '?'} size={36} />
              <div>
                <div className="ol-mail-from-name">{selected.sender}</div>
                <div className="ol-mail-from-time">
                  {selected.timestamp && new Date(selected.timestamp).toLocaleString()}
                </div>
              </div>
            </div>
            {/* ── Action row (above body so always visible) ── */}
            <div className="ol-mail-actions">
              <button className="btn btn-secondary" onClick={() => {
                setForm({ to: selected.sender, subject: `Re: ${selected.subject}`, body: '' });
                setReplyToId(selected.id);
                setComposing(true);
              }}>
                <Send size={13}/> Reply
              </button>
              <button className="btn btn-ai" onClick={() => runAI('classify')} disabled={!!aiLoading} id="outlook-classify-btn">
                {aiLoading === 'classify' ? <Loader2 size={13} className="ol-spin"/> : <Tag size={13}/>}
                Classify
              </button>
              <button className="btn btn-ai" onClick={() => runAI('summarize')} disabled={!!aiLoading} id="outlook-summarize-btn">
                {aiLoading === 'summarize' ? <Loader2 size={13} className="ol-spin"/> : <FileText size={13}/>}
                Summarize
              </button>
              <div className="ol-draft-group">
                <select className="ol-quality-select" value={draftQuality} onChange={e => setDraftQuality(e.target.value)}>
                  <option value="quick">Quick</option>
                  <option value="balanced">Balanced</option>
                  <option value="thorough">Thorough</option>
                </select>
                <button className="btn btn-ai btn-ai-primary" onClick={() => runAI('draft')} disabled={!!aiLoading} id="outlook-draft-btn">
                  {aiLoading === 'draft' ? <Loader2 size={13} className="ol-spin"/> : <Sparkles size={13}/>}
                  AI Draft Reply
                </button>
              </div>
              <button className="btn btn-ai btn-cal" onClick={() => runAI('calendar')} disabled={!!aiLoading} id="outlook-add-cal-btn" title="AI extracts meeting from email and adds to calendar">
                {aiLoading === 'calendar' ? <Loader2 size={13} className="ol-spin"/> : <CalendarPlus size={13}/>}
                Add to Calendar
              </button>
            </div>

            {/* ── Email Thread ────────────────────────────────── */}
            <div className="ol-mail-thread">
              {loadingThread ? (
                <div className="ol-thread-loading">
                  <Loader2 className="ol-spin" size={16}/>
                  <span>Loading thread...</span>
                </div>
              ) : (
                (() => {
                  const displayMessages = (threadMessages.length === 1 && threadMessages[0].sub_messages?.length > 0)
                    ? threadMessages[0].sub_messages
                    : threadMessages;

                  return displayMessages.map((msg, idx) => {
                    const isMe = msg.sender === currentUser?.mail || msg.sender === currentUser?.userPrincipalName;
                    return (
                      <div key={msg.id || idx} className={`ol-thread-message ${isMe ? 'ol-sent-by-me' : ''}`}>
                        <div className="ol-thread-message-header">
                          <Avatar name={msg.sender || '?'} size={28} />
                          <div className="ol-thread-message-meta">
                            <span className="ol-thread-message-sender">
                              {isMe ? 'You' : msg.sender}
                            </span>
                            <span className="ol-thread-message-time">
                              {msg.timestamp && new Date(msg.timestamp).toLocaleString()}
                            </span>
                          </div>
                        </div>
                        <div className="ol-thread-message-body" style={{ whiteSpace: 'pre-wrap' }}>
                          {msg.body || msg.snippet}
                        </div>
                      </div>
                    );
                  });
                })()
              )}
            </div>

            {/* ── AI results panel ───────────────────────────── */}
            {aiError && <div className="ol-ai-error"><AlertCircle size={14}/> {aiError}</div>}

            {aiClassification && (
              <div className="ol-ai-panel">
                <div className="ol-ai-panel-title"><Tag size={13}/> Classification</div>
                <div className="ol-ai-chips">
                  <span className="ol-ai-chip" style={{ background: PRIORITY_COLORS[aiClassification.priority] || '#6366f1' }}>
                    {aiClassification.priority?.toUpperCase()}
                  </span>
                  <span className="ol-ai-chip ol-ai-chip-cat">{aiClassification.category}</span>
                  {aiClassification.confidence != null && (
                    <span className="ol-ai-chip ol-ai-chip-conf">{Math.round(aiClassification.confidence * 100)}% confident</span>
                  )}
                </div>
                {aiClassification.reasoning && (
                  <div className="ol-ai-reasoning">{aiClassification.reasoning}</div>
                )}
              </div>
            )}

            {aiSummary && (
              <div className="ol-ai-panel">
                <div className="ol-ai-panel-title"><FileText size={13}/> AI Summary</div>
                <div className="ol-ai-summary-text">{aiSummary}</div>
              </div>
            )}

            {aiCalEvent && (
              <div className="ol-ai-panel ol-ai-panel-cal">
                <div className="ol-ai-panel-title"><CalendarPlus size={13}/> Added to Calendar</div>
                <div className="ol-cal-event-info">
                  <div className="ol-cal-event-title">📅 {aiCalEvent.title}</div>
                  <div className="ol-cal-event-time">
                    {aiCalEvent.start && new Date(aiCalEvent.start).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    {aiCalEvent.end && ` → ${new Date(aiCalEvent.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
                  </div>
                  {aiCalEvent.attendees?.length > 0 && (
                    <div className="ol-cal-attendees">
                      {aiCalEvent.attendees.map((a, i) => <span key={i} className="ol-attendee-chip">{a.split('@')[0]}</span>)}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="empty-state">
            <Mail size={44} />
            <p className="empty-state-title">Select a message</p>
            <p className="empty-state-desc">Choose an email from the list to read it, or compose a new one.</p>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Calendar Tab ───────────────────────────────────────────────────────── */
function CalendarTab() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ subject: '', start_iso: '', end_iso: '', body: '', attendees: '' });
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await gfetch('/calendar/today?days_ahead=30');
      setEvents(d.events || []);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const handleCreate = async () => {
    if (!form.subject.trim()) { showToast('Please enter a subject', 'error'); return; }
    if (!form.start_iso || !form.end_iso) { showToast('Please select start and end time', 'error'); return; }
    // Convert datetime-local value ("2026-07-10T09:00") to full ISO string
    const startISO = new Date(form.start_iso).toISOString();
    const endISO = new Date(form.end_iso).toISOString();
    if (isNaN(new Date(startISO))) { showToast('Invalid start time', 'error'); return; }
    if (isNaN(new Date(endISO))) { showToast('Invalid end time', 'error'); return; }
    setSaving(true);
    try {
      await gfetch('/calendar/events', {
        method: 'POST',
        body: JSON.stringify({
          subject: form.subject,
          start_iso: startISO,
          end_iso: endISO,
          body: form.body,
          attendees: form.attendees ? form.attendees.split(',').map(s => s.trim()).filter(Boolean) : [],
        }),
      });
      showToast('✅ Event created!');
      setShowForm(false);
      setForm({ subject: '', start_iso: '', end_iso: '', body: '', attendees: '' });
      load();
    } catch (e) { showToast(`❌ ${e.message}`, 'error'); }
    finally { setSaving(false); }
  };

  return (
    <div className="ol-section-page">
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}
      <div className="ol-section-header">
        <span className="ol-section-title"><Calendar size={14}/> Upcoming 30 Days</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={() => setShowForm(v => !v)} id="outlook-new-event-btn">
            <Plus size={13}/> New Event
          </button>
          <button className="btn-icon" onClick={load}><RefreshCw size={14}/></button>
        </div>
      </div>

      {showForm && (
        <div className="ol-form-card glass-card">
          <div className="ol-form-title">Create Calendar Event</div>
          <input className="input" placeholder="Subject" value={form.subject} onChange={e => setForm(f => ({ ...f, subject: e.target.value }))} />
          <div className="ol-form-row">
            <div>
              <label className="ol-label">Start (ISO)</label>
              <input className="input" type="datetime-local" value={form.start_iso}
                onChange={e => setForm(f => ({ ...f, start_iso: e.target.value }))} />
            </div>
            <div>
              <label className="ol-label">End (ISO)</label>
              <input className="input" type="datetime-local" value={form.end_iso}
                onChange={e => setForm(f => ({ ...f, end_iso: e.target.value }))} />
            </div>
          </div>
          <input className="input" placeholder="Attendees (comma-separated emails)" value={form.attendees}
            onChange={e => setForm(f => ({ ...f, attendees: e.target.value }))} />
          <textarea className="input" rows={3} placeholder="Description (optional)" value={form.body}
            onChange={e => setForm(f => ({ ...f, body: e.target.value }))} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreate} disabled={saving}>
              {saving ? <Loader2 size={13} className="ol-spin"/> : <CheckCircle2 size={13}/>}
              {saving ? 'Creating…' : 'Create Event'}
            </button>
            <button className="btn btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </div>
      )}

      {loading && <SectionLoader />}
      {error && <ErrorCard msg={error} onRetry={load} />}
      {!loading && !error && events.length === 0 && (
        <div className="empty-state"><Calendar size={44}/><p className="empty-state-title">No upcoming events in the next 30 days</p></div>
      )}
      <div className="ol-event-grid">
        {events.map((ev, i) => {
          const start = ev.start?.dateTime || ev.start;
          const end = ev.end?.dateTime || ev.end;
          return (
            <div key={ev.id || i} className="ol-event-card glass-card">
              <div className="ol-event-bar" />
              <div className="ol-event-content">
                <div className="ol-event-title">{ev.subject || ev.title || '(No title)'}</div>
                <div className="ol-event-time">
                  <Clock size={12}/>
                  {start ? new Date(start).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }) + ' · ' + new Date(start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                  {end ? ` → ${new Date(end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}
                </div>
                {ev.location?.displayName && (
                  <div className="ol-event-location">📍 {ev.location.displayName}</div>
                )}
                {(ev.attendees || []).length > 0 && (
                  <div className="ol-event-attendees">
                    {ev.attendees.slice(0, 3).map((a, j) => (
                      <span key={j} className="ol-attendee-chip">
                        {(a.emailAddress?.address || a).split('@')[0]}
                      </span>
                    ))}
                    {ev.attendees.length > 3 && <span className="ol-attendee-chip">+{ev.attendees.length - 3}</span>}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Contacts Tab ───────────────────────────────────────────────────────── */
function ContactsTab() {
  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await gfetch('/contacts?top=30');
      setContacts(d.contacts || []);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = contacts.filter(c =>
    (c.displayName || c.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (c.emailAddresses?.[0]?.address || c.email || '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="ol-section-page">
      <div className="ol-section-header">
        <span className="ol-section-title"><Users size={14}/> Contacts ({contacts.length})</span>
        <button className="btn-icon" onClick={load}><RefreshCw size={14}/></button>
      </div>
      <div className="ol-search-bar">
        <Search size={14}/>
        <input className="ol-search-input" placeholder="Search contacts…" value={search}
          onChange={e => setSearch(e.target.value)} />
      </div>

      {loading && <SectionLoader />}
      {error && <ErrorCard msg={error} onRetry={load} />}
      {!loading && !error && filtered.length === 0 && (
        <div className="empty-state"><Users size={44}/><p className="empty-state-title">No contacts found</p></div>
      )}
      <div className="ol-contacts-grid">
        {filtered.map((c, i) => {
          const name = c.displayName || c.name || 'Unknown';
          const email = c.emailAddresses?.[0]?.address || c.email || '';
          const phone = c.mobilePhone || c.phones?.[0]?.number || '';
          return (
            <div key={c.id || i} className="ol-contact-card glass-card">
              <Avatar name={name} size={42} />
              <div className="ol-contact-info">
                <div className="ol-contact-name">{name}</div>
                {email && <div className="ol-contact-email">{email}</div>}
                {phone && <div className="ol-contact-phone">{phone}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Files Tab ──────────────────────────────────────────────────────────── */
function FilesTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await gfetch('/drive/items?top=25');
      setItems(d.items || []);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const icon = item => item.folder ? '📁' : '📄';
  const size = bytes => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  return (
    <div className="ol-section-page">
      <div className="ol-section-header">
        <span className="ol-section-title"><HardDrive size={14}/> OneDrive Files</span>
        <button className="btn-icon" onClick={load}><RefreshCw size={14}/></button>
      </div>

      {loading && <SectionLoader />}
      {error && <ErrorCard msg={error} onRetry={load} />}
      {!loading && !error && items.length === 0 && (
        <div className="empty-state"><HardDrive size={44}/><p className="empty-state-title">No files found</p></div>
      )}
      <div className="ol-files-list glass-card">
        {items.map((item, i) => (
          <div key={item.id || i} className="ol-file-row">
            <span className="ol-file-icon">{icon(item)}</span>
            <div className="ol-file-info">
              <div className="ol-file-name">{item.name}</div>
              <div className="ol-file-meta">
                {item.lastModifiedDateTime && new Date(item.lastModifiedDateTime).toLocaleDateString()}
                {item.size && ` · ${size(item.size)}`}
              </div>
            </div>
            {item.webUrl && (
              <a href={item.webUrl} target="_blank" rel="noopener noreferrer"
                className="btn btn-secondary" style={{ fontSize: 11, padding: '4px 10px' }}>
                Open <ChevronRight size={11}/>
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Profile Tab ────────────────────────────────────────────────────────── */
function ProfileTab() {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    gfetch('/users/me')
      .then(setProfile)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <SectionLoader />;
  if (error) return <ErrorCard msg={error} />;
  if (!profile) return null;

  const fields = [
    ['Display Name', profile.displayName],
    ['Email', profile.mail || profile.userPrincipalName],
    ['Job Title', profile.jobTitle],
    ['Department', profile.department],
    ['Office', profile.officeLocation],
    ['Phone', profile.mobilePhone || profile.businessPhones?.[0]],
  ].filter(([, v]) => v);

  return (
    <div className="ol-section-page">
      <div className="ol-profile-card glass-card">
        <Avatar name={profile.displayName || 'U'} size={72} />
        <div className="ol-profile-name">{profile.displayName}</div>
        <div className="ol-profile-email">{profile.mail || profile.userPrincipalName}</div>
        <div className="ol-profile-fields">
          {fields.map(([label, value]) => (
            <div key={label} className="ol-profile-field">
              <span className="ol-label">{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── Groups Tab ─────────────────────────────────────────────────────────── */
function GroupsTab() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await gfetch('/groups?top=20');
      setGroups(d.groups || []);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="ol-section-page">
      <div className="ol-section-header">
        <span className="ol-section-title"><Layers size={14}/> Groups ({groups.length})</span>
        <button className="btn-icon" onClick={load}><RefreshCw size={14}/></button>
      </div>
      {loading && <SectionLoader />}
      {error && <ErrorCard msg={error} onRetry={load} />}
      {!loading && !error && groups.length === 0 && (
        <div className="empty-state"><Layers size={44}/><p className="empty-state-title">No groups found</p></div>
      )}
      <div className="ol-groups-list">
        {groups.map((g, i) => (
          <div key={g.id || i} className="ol-group-card glass-card">
            <Avatar name={g.displayName || 'G'} size={40} />
            <div className="ol-group-info">
              <div className="ol-group-name">{g.displayName}</div>
              {g.description && <div className="ol-group-desc">{g.description}</div>}
              {g.mail && <div className="ol-group-mail">{g.mail}</div>}
            </div>
            <span className="ol-group-type-badge">{g.groupTypes?.includes('Unified') ? 'M365' : 'Security'}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Teams Tab ──────────────────────────────────────────────────────────── */
function TeamsTab() {
  const [channelId, setChannelId] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState(null);
  const [presence, setPresence] = useState(null);
  const [presenceEmail, setPresenceEmail] = useState('');
  const [loadingPresence, setLoadingPresence] = useState(false);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleSend = async () => {
    if (!channelId || !message) return;
    setSending(true);
    try {
      await gfetch('/teams/notify', {
        method: 'POST',
        body: JSON.stringify({ channel_id: channelId, message }),
      });
      showToast('Teams message sent!');
      setMessage('');
    } catch (e) { showToast(e.message, 'error'); }
    finally { setSending(false); }
  };

  const handlePresence = async () => {
    if (!presenceEmail) return;
    setLoadingPresence(true);
    try {
      const d = await gfetch(`/presence/${encodeURIComponent(presenceEmail)}`);
      setPresence(d);
    } catch (e) { showToast(e.message, 'error'); }
    finally { setLoadingPresence(false); }
  };

  const presenceColor = av => ({
    Available: '#10b981', Busy: '#f43f5e', Away: '#f97316', DoNotDisturb: '#f43f5e',
  }[av] || '#6b7280');

  return (
    <div className="ol-section-page">
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}

      {/* Send Teams message */}
      <div className="ol-form-card glass-card">
        <div className="ol-form-title"><MessageSquare size={14}/> Send Teams Channel Message</div>
        <input className="input" placeholder="Channel ID (e.g. 19:xxx@thread.tacv2)"
          value={channelId} onChange={e => setChannelId(e.target.value)} />
        <textarea className="input" rows={4} placeholder="Message…"
          value={message} onChange={e => setMessage(e.target.value)} />
        <button className="btn btn-primary" onClick={handleSend} disabled={sending || !channelId || !message}
          id="outlook-teams-send-btn">
          {sending ? <Loader2 size={13} className="ol-spin"/> : <Send size={13}/>}
          {sending ? 'Sending…' : 'Send to Teams'}
        </button>
      </div>

      {/* Presence lookup */}
      <div className="ol-form-card glass-card" style={{ marginTop: 16 }}>
        <div className="ol-form-title"><User size={14}/> Check User Presence</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input className="input" placeholder="user@domain.com"
            value={presenceEmail} onChange={e => setPresenceEmail(e.target.value)} />
          <button className="btn btn-secondary" onClick={handlePresence}
            disabled={loadingPresence || !presenceEmail} style={{ flexShrink: 0 }}>
            {loadingPresence ? <Loader2 size={13} className="ol-spin"/> : 'Check'}
          </button>
        </div>
        {presence && (
          <div className="ol-presence-result">
            <span className="ol-presence-dot" style={{ background: presenceColor(presence.availability) }}/>
            <span className="ol-presence-status">{presence.availability || 'Unknown'}</span>
            {presence.activity && <span className="ol-presence-activity">· {presence.activity}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Main OutlookPage ───────────────────────────────────────────────────── */
export default function OutlookPage() {
  const [tab, setTab] = useState('mail');
  const [graphStatus, setGraphStatus] = useState(null);

  useEffect(() => {
    gfetch('/status').then(setGraphStatus).catch(() => {});
  }, []);

  const renderTab = () => {
    switch (tab) {
      case 'mail':     return <MailTab />;
      case 'calendar': return <CalendarTab />;
      case 'contacts': return <ContactsTab />;
      case 'files':    return <FilesTab />;
      case 'profile':  return <ProfileTab />;
      case 'groups':   return <GroupsTab />;
      case 'teams':    return <TeamsTab />;
      default:         return null;
    }
  };

  return (
    <div className="outlook-page" id="outlook-page">
      {/* Header */}
      <div className="ol-header animate-fade-in">
        <div className="ol-header-left">
          <div className="ol-header-icon">
            <Mail size={20}/>
          </div>
          <div>
            <h1 className="ol-title">Microsoft Graph</h1>
            <p className="ol-subtitle">Outlook · Teams · OneDrive · Contacts</p>
          </div>
        </div>
        {graphStatus && <StatusBadge mode={graphStatus.mode} />}
      </div>

      {/* Tab bar */}
      <div className="ol-tabs animate-slide-up">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`ol-tab ${tab === id ? 'ol-tab-active' : ''}`}
            onClick={() => setTab(id)}
            id={`outlook-tab-${id}`}
          >
            <Icon size={14}/>
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="ol-content animate-slide-up">
        {renderTab()}
      </div>
    </div>
  );
}
