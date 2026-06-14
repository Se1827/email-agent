import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mail, MailWarning, CheckCircle2, Star,
  AlertTriangle, Bell, Clock, CalendarDays,
  ArrowRight, Sparkles, Link2, ShieldCheck,
  TrendingUp, Zap, X, ListChecks, CheckCircle, XCircle,
  Brain, Sunrise, MessageSquare, Target, Lightbulb,
  AlertCircle, FileEdit, Crown, RefreshCw,
  CalendarPlus, Plus, Loader,
} from 'lucide-react';
import {
  fetchDashboard, dismissNotification, fetchDailyDigest,
  fetchActionItems, updateActionItem, request,
  triggerDigestGeneration, digestCardAction,
} from '../api';
import './Dashboard.css';

const PRIORITY_COLORS = {
  critical: '#f43f5e',
  high: '#f97316',
  normal: '#6366f1',
  low: '#6b7280',
};

const SEVERITY_ICONS = {
  critical: AlertTriangle,
  warning: Bell,
  info: Sparkles,
};

const NUDGE_ICONS = {
  overdue: AlertCircle,
  stale_draft: FileEdit,
  vip: Crown,
  reminder: Bell,
};

function UrgencyRing({ score }) {
  const circumference = 2 * Math.PI * 20;
  const filled = (score / 10) * circumference;
  const level = score <= 2 ? 'low' : score <= 5 ? 'moderate' : score <= 7 ? 'high' : 'critical';
  const levelLabel = score <= 2 ? 'All Clear' : score <= 5 ? 'Moderate' : score <= 7 ? 'Busy' : 'Critical';
  const color = score <= 2 ? '#22c55e' : score <= 5 ? '#f59e0b' : score <= 7 ? '#f97316' : '#ef4444';

  return (
    <div className="digest-urgency-bar">
      <div className="urgency-ring">
        <svg width="48" height="48" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4" />
          <circle cx="24" cy="24" r="20" fill="none" stroke={color} strokeWidth="4"
            strokeDasharray={`${filled} ${circumference}`}
            strokeLinecap="round" transform="rotate(-90 24 24)"
            style={{ transition: 'stroke-dasharray 1s ease', filter: `drop-shadow(0 0 4px ${color}40)` }}
          />
        </svg>
        <span className="urgency-ring-label">{score}</span>
      </div>
      <div className="urgency-info">
        <div className={`urgency-level urgency-${level}`}>{levelLabel}</div>
        <div className="urgency-desc">Inbox urgency score</div>
      </div>
    </div>
  );
}

// ── Deadline term highlight helper ────────────────────────────────────────
function DeadlineHighlight({ text, terms }) {
  if (!text || !terms || terms.length === 0) return <span>{text}</span>;
  // Build regex from terms
  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(pattern);
  return (
    <span>
      {parts.map((part, i) =>
        terms.some(t => t.toLowerCase() === part.toLowerCase())
          ? <mark key={i} className="deadline-pill">{part}</mark>
          : <span key={i}>{part}</span>
      )}
    </span>
  );
}

// ── Email Digest Card ─────────────────────────────────────────────────────
const URGENCY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  normal: '#6366f1',
  low: '#6b7280',
};

function EmailDigestCard({ card, onNavigate }) {
  const [actionLoading, setActionLoading] = useState(null);
  const [actionDone, setActionDone] = useState({});

  const rawUrgency = card.urgency || card.priority || 'normal';
  const urgency = rawUrgency === 'unclassified' ? 'normal' : rawUrgency;
  const borderColor = URGENCY_COLORS[urgency] || URGENCY_COLORS.normal;
  const senderInitial = (card.sender || '?').charAt(0).toUpperCase();
  const senderName = card.sender?.split('@')[0] || card.sender;

  const handleCardAction = async (actionType, actionData) => {
    setActionLoading(actionType);
    try {
      await digestCardAction(card.id, actionType, actionData);
      setActionDone(prev => ({ ...prev, [actionType]: true }));
    } catch (err) {
      console.error('Card action failed:', err);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="digest-email-card" style={{ '--card-urgency': borderColor }}>
      {/* Header: Avatar + Subject + Time */}
      <div className="digest-card-header" onClick={onNavigate}>
        <div className="digest-card-avatar" style={{ background: borderColor }}>
          {senderInitial}
          {card.thread_count > 1 && (
            <span className="digest-thread-badge">{card.thread_count}</span>
          )}
        </div>
        <div className="digest-card-meta">
          <div className="digest-card-subject">{card.subject || 'No subject'}</div>
          <div className="digest-card-sender-row">
            <span className="digest-card-sender">{senderName}</span>
            {card.time_since && <span className="digest-card-time">{card.time_since}</span>}
          </div>
        </div>
        <div style={{display:'flex',gap:4,flexShrink:0,flexDirection:'column',alignItems:'flex-end'}}>
          <span className={`digest-urgency-chip urgency-${urgency}`}>{urgency}</span>
          {card.category && card.category !== 'unknown' && (
            <span className={`digest-category-chip cat-${card.category}`}>{card.category}</span>
          )}
        </div>
      </div>

      {/* AI Classification Summary */}
      {card.reasoning && (
        <div className="digest-card-reasoning" onClick={onNavigate}>
          <Brain size={11} /> {card.reasoning}
        </div>
      )}

      {/* Preview with deadline highlighting */}
      {card.preview && (
        <div className="digest-card-preview" onClick={onNavigate}>
          <DeadlineHighlight text={card.preview} terms={card.deadline_terms || []} />
        </div>
      )}

      {/* Deadline terms pills (standalone if no preview) */}
      {!card.preview && card.deadline_terms?.length > 0 && (
        <div className="digest-card-deadlines">
          {card.deadline_terms.map((term, i) => (
            <span key={i} className="deadline-pill">{term}</span>
          ))}
        </div>
      )}

      {/* Why / reasoning (fallback for old format) */}
      {card.why && !card.preview && !card.reasoning && (
        <div className="digest-card-why">{card.why}</div>
      )}

      {/* Suggested Actions */}
      {(card.suggested_actions?.length > 0 || card.deadline_terms?.length > 0) && (
        <div className="digest-card-actions">
          {card.suggested_actions?.map((sa, i) => (
            <button
              key={i}
              className={`digest-action-btn ${actionDone[sa.type + i] ? 'done' : ''}`}
              disabled={!!actionLoading || actionDone[sa.type + i]}
              onClick={(e) => {
                e.stopPropagation();
                const isAlreadyDone = sa.already_done;
                const data = sa.type === 'calendar'
                  ? { title: sa.label, date: sa.date || new Date().toISOString() }
                  : { description: sa.label };
                if (!isAlreadyDone) handleCardAction(sa.type, data);
              }}
            >
              {sa.type === 'calendar' ? <CalendarPlus size={12} /> : <Plus size={12} />}
              {sa.already_done ? sa.label : actionLoading === sa.type ? 'Adding...' : actionDone[sa.type + i] ? 'Added ✓' : sa.label}
            </button>
          ))}
          {/* Default buttons if no suggested_actions but has deadlines */}
          {(!card.suggested_actions || card.suggested_actions.length === 0) && card.id && (
            <>
              <button
                className={`digest-action-btn ${card.has_existing_event || actionDone.calendar ? 'done' : ''}`}
                disabled={!!actionLoading || actionDone.calendar || card.has_existing_event}
                onClick={(e) => {
                  e.stopPropagation();
                  handleCardAction('calendar', { title: card.subject, date: new Date().toISOString() });
                }}
              >
                <CalendarPlus size={12} />
                {card.has_existing_event ? 'Already in calendar ✓' : actionLoading === 'calendar' ? 'Adding...' : actionDone.calendar ? 'Added ✓' : 'Add to Calendar'}
              </button>
              <button
                className={`digest-action-btn ${card.has_existing_action || actionDone.action ? 'done' : ''}`}
                disabled={!!actionLoading || actionDone.action || card.has_existing_action}
                onClick={(e) => {
                  e.stopPropagation();
                  handleCardAction('action', { description: `Follow up on: ${card.subject}` });
                }}
              >
                <Plus size={12} />
                {card.has_existing_action ? 'Action exists ✓' : actionLoading === 'action' ? 'Adding...' : actionDone.action ? 'Added ✓' : 'Create Action'}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}


function Dashboard() {
  const [data, setData] = useState(null);
  const [graphStatus, setGraphStatus] = useState(null);
  const [digest, setDigest] = useState(null);
  const [digestLoading, setDigestLoading] = useState(false);
  const [digestDays, setDigestDays] = useState(0);
  const [actionItems, setActionItems] = useState([]);
  const [allActionItems, setAllActionItems] = useState([]);
  const [actionsLoading, setActionsLoading] = useState(false);

  useEffect(() => {
    request("/graph/status").then(j => setGraphStatus(j)).catch(() => {});
  }, []);

  const [loading, setLoading] = useState(true);

  const navigate = useNavigate();

  useEffect(() => {
    loadDashboard();
    loadActionItems();

    // Auto-load digest (check cache first)
    const cached = sessionStorage.getItem('daily_digest');
    if (cached) {
      try { setDigest(JSON.parse(cached)); } catch (_) { loadDigest(); }
    } else {
      loadDigest();
    }

    // Background polling every 30s (light dashboard stats only, not LLM calls)
    const interval = setInterval(() => {
      fetchDashboard()
        .then(d => setData(d))
        .catch(err => console.error('Auto-fetch failed:', err));
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const loadDashboard = async () => {
    try {
      const d = await fetchDashboard();
      setData(d);
    } catch (err) {
      console.error('Dashboard load failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadDigest = async (days) => {
    const d_days = days !== undefined ? days : digestDays;
    setDigestLoading(true);
    try {
      const d = await fetchDailyDigest(d_days);
      setDigest(d);
      sessionStorage.setItem('daily_digest', JSON.stringify(d));
    } catch (err) {
      console.error('Digest load failed:', err);
    } finally {
      setDigestLoading(false);
    }
  };

  const loadActionItems = async () => {
    setActionsLoading(true);
    try {
      const pending = await fetchActionItems('pending');
      setActionItems(pending);
      // Also load completed for progress bar
      const all = await fetchActionItems();
      setAllActionItems(all);
    } catch (err) {
      console.error('Actions load failed:', err);
    } finally {
      setActionsLoading(false);
    }
  };

  const handleActionUpdate = async (id, status) => {
    try {
      await updateActionItem(id, status);
      setActionItems(prev => prev.map(a => a.id === id ? {...a, status} : a));
      setAllActionItems(prev => prev.map(a => a.id === id ? {...a, status} : a));
    } catch (err) { console.error('Action update failed:', err); }
  };

  const handleDismiss = async (id) => {
    try {
      await dismissNotification(id);
      setData(prev => ({
        ...prev,
        notifications: prev.notifications.filter(n => n.id !== id),
      }));
    } catch (_) { /* ignore */ }
  };

  if (loading) {
    return (
      <div className="dashboard">
        <div className="dashboard-loading">
          <div className="shimmer-bg" style={{ width: 200, height: 24, borderRadius: 8 }} />
          <div className="dashboard-grid">
            {[1,2,3,4].map(i => (
              <div key={i} className="stat-card shimmer-bg" style={{ height: 110 }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="dashboard">
        <div className="empty-state">
          <Mail size={48} />
          <p className="empty-state-title">Could not load dashboard</p>
          <button className="btn btn-primary" onClick={loadDashboard}>Retry</button>
        </div>
      </div>
    );
  }

  const totalPriority = Object.values(data.priority_breakdown).reduce((a, b) => a + b, 0) || 1;

  // Action items progress
  const pendingActions = actionItems.filter(a => a.status === 'pending');
  const completedCount = allActionItems.filter(a => a.status === 'completed').length;
  const totalActions = allActionItems.length;
  const progressPct = totalActions > 0 ? Math.round((completedCount / totalActions) * 100) : 0;

  return (
    <div className="dashboard" id="dashboard-page">
      <div className="dashboard-header animate-fade-in">
        <div>
          <h1 className="dashboard-title">Dashboard</h1>
          <p className="dashboard-subtitle">Your intelligent email command center</p>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/inbox')}>
          <Mail size={15} /> Go to Inbox <ArrowRight size={14} />
        </button>
      </div>

      {/* ---- Stat Cards ---- */}
      <div className="dashboard-grid animate-slide-up">
        <div className="stat-card stat-card-accent" style={{'--card-accent': '#6366f1'}}>
          <div className="stat-card-icon"><Mail size={20} /></div>
          <div className="stat-card-value">{data.total_emails}</div>
          <div className="stat-card-label">Total Emails</div>
        </div>
        <div className="stat-card stat-card-accent" style={{'--card-accent': '#f97316'}}>
          <div className="stat-card-icon"><MailWarning size={20} /></div>
          <div className="stat-card-value">{data.unread_count}</div>
          <div className="stat-card-label">Needs Attention</div>
        </div>
        <div className="stat-card stat-card-accent" style={{'--card-accent': '#10b981'}}>
          <div className="stat-card-icon"><CheckCircle2 size={20} /></div>
          <div className="stat-card-value">{data.classified_count}<span className="stat-card-sub">/{data.total_emails}</span></div>
          <div className="stat-card-label">AI Classified</div>
        </div>
        <div className="stat-card stat-card-accent" style={{'--card-accent': '#fbbf24'}}>
          <div className="stat-card-icon"><Star size={20} /></div>
          <div className="stat-card-value">{data.starred_count}</div>
          <div className="stat-card-label">Starred</div>
        </div>
      </div>

      <div className="dashboard-body">
        {/* ---- Left Column ---- */}
        <div className="dashboard-col-main">
          {/* ---- AI Daily Digest ---- */}
          <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.05s'}}>
            <div className="section-heading-row">
              <h2 className="section-heading"><Sunrise size={13} /> Daily Digest</h2>
              <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
                {/* Date range selector */}
                <div className="digest-day-selector">
                  {[{v:0,l:'Today'},{v:1,l:'2 Days'},{v:2,l:'3 Days'}].map(opt => (
                    <button key={opt.v}
                      className={`digest-day-btn ${digestDays === opt.v ? 'active' : ''}`}
                      disabled={digestLoading}
                      onClick={() => { setDigestDays(opt.v); loadDigest(opt.v); }}
                    >{opt.l}</button>
                  ))}
                </div>
                {digest?.generated_at && (
                  <span className="digest-status-badge">
                    <Clock size={10} /> {new Date(digest.generated_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
                    {digest.auto_classified && <span className="digest-auto-badge">AI-Rich</span>}
                  </span>
                )}
                <button className="btn-link" onClick={() => loadDigest()} disabled={digestLoading}>
                  <RefreshCw size={12} className={digestLoading ? 'spin' : ''} style={{marginRight: 4}} />
                  {digestLoading ? 'Generating...' : 'Refresh'}
                </button>
              </div>
            </div>
            {digestLoading && !digest ? (
              <div className="digest-card glass-card">
                <div className="digest-loading-state">
                  <div className="digest-loading-line" style={{width: '70%'}} />
                  <div className="digest-loading-line" style={{width: '100%'}} />
                  <div className="digest-loading-line" style={{width: '85%'}} />
                  <div className="digest-loading-line" style={{width: '60%'}} />
                  <div className="digest-loading-line" style={{width: '90%'}} />
                </div>
              </div>
            ) : digest ? (
              <div className="digest-card glass-card">
                {/* Greeting */}
                <div className="digest-greeting">
                  <Brain size={16} className="digest-brain-icon" />
                  <span>{digest.greeting}</span>
                  {digest.emails_in_digest !== undefined && (
                    <span className="digest-count-badge" style={{marginLeft:'auto'}}>
                      {digest.emails_in_digest} actionable / {digest.total_emails} total
                    </span>
                  )}
                </div>

                {/* All Clear Celebration */}
                {digest.all_clear ? (
                  <div className="digest-all-clear">
                    <div className="digest-all-clear-icon">☀️</div>
                    <div className="digest-all-clear-title">You're all caught up!</div>
                    <div className="digest-all-clear-sub">{digest.one_line}</div>

                    {/* Still show calendar even when all clear */}
                    {digest.calendar_today?.length > 0 && (
                      <div className="digest-section" style={{marginTop: 16, width: '100%'}}>
                        <h4 className="digest-section-title"><CalendarDays size={12} /> Today's Schedule</h4>
                        <div className="digest-schedule">
                          {digest.calendar_today.map((c, i) => (
                            <div key={i} className="digest-schedule-item"
                              onClick={() => navigate('/calendar')}
                              style={{cursor: 'pointer'}}>
                              <span className="schedule-time">{c.time || '—'}</span>
                              <span className="schedule-dot" />
                              <span className="schedule-title">{c.title || c}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {digest.tip && (
                      <div className="digest-tip" style={{marginTop: 12}}>
                        <Lightbulb size={14} />
                        <span>{digest.tip}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    {/* Urgency Score */}
                    {digest.urgency_score !== undefined && (
                      <UrgencyRing score={digest.urgency_score} />
                    )}

                    {/* One-liner */}
                    {digest.one_line && (
                      <div className="digest-oneliner">{digest.one_line}</div>
                    )}

                    {/* Email Digest Cards */}
                    {(digest.email_cards?.length > 0 || digest.priority_emails?.length > 0) && (
                      <div className="digest-section">
                        <h4 className="digest-section-title"><Target size={12} /> Your Email Digest
                          <span className="digest-count-badge">
                            {(digest.email_cards || digest.priority_emails || []).length} emails
                          </span>
                        </h4>
                        <div className="digest-email-cards">
                          {(digest.email_cards || digest.priority_emails || []).map((card, i) => (
                            <EmailDigestCard
                              key={card.id || i}
                              card={card}
                              onNavigate={() => navigate(card.id ? `/inbox?email=${encodeURIComponent(card.id)}` : '/inbox')}
                            />
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Themes */}
                    {digest.themes?.length > 0 && (
                      <div className="digest-section">
                        <h4 className="digest-section-title"><MessageSquare size={12} /> Themes</h4>
                        <div className="digest-themes">
                          {digest.themes.map((t, i) => (
                            <div key={i} className="digest-theme-chip" title={t.summary}>
                              <span className="digest-theme-name">{t.theme}</span>
                              <span className="digest-theme-count">{t.count}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Nudges */}
                    {digest.nudges?.length > 0 && (
                      <div className="digest-section">
                        <h4 className="digest-section-title"><AlertTriangle size={12} /> Nudges</h4>
                        {digest.nudges.map((n, i) => {
                          const nudgeType = n.type || 'reminder';
                          const NudgeIcon = NUDGE_ICONS[nudgeType] || Zap;
                          return (
                            <div key={i} className={`digest-nudge nudge-${nudgeType}`}>
                              <NudgeIcon size={13} className="nudge-icon" />
                              <span>{n.text || n}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Today's Schedule (Timeline) */}
                    {digest.calendar_today?.length > 0 && (
                      <div className="digest-section">
                        <h4 className="digest-section-title"><CalendarDays size={12} /> Today's Schedule</h4>
                        <div className="digest-schedule">
                          {digest.calendar_today.map((c, i) => (
                            <div key={i} className="digest-schedule-item"
                              onClick={() => navigate('/calendar')}
                              style={{cursor: 'pointer'}}>
                              <span className="schedule-time">{c.time || '—'}</span>
                              <span className="schedule-dot" />
                              <span className="schedule-title">{c.title || c}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Tip */}
                    {digest.tip && (
                      <div className="digest-tip">
                        <Lightbulb size={14} />
                        <span>{digest.tip}</span>
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div className="digest-card glass-card digest-empty">
                <Brain size={24} />
                <p>Loading your daily brief...</p>
              </div>
            )}
          </section>

          {/* Notifications */}
          {data.notifications.length > 0 && (
            <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.1s'}}>
              <h2 className="section-heading"><Zap size={13} /> AI Alerts & Notifications</h2>
              <div className="notification-list">
                {data.notifications.map((n) => {
                  const SevIcon = SEVERITY_ICONS[n.severity] || Bell;
                  return (
                    <div
                      key={n.id}
                      className={`notification-card notification-${n.severity}`}
                      onClick={() => {
                        if (n.related_type === 'email') navigate('/inbox');
                        else if (n.related_type === 'event') navigate('/calendar');
                      }}
                    >
                      <div className={`notification-icon notification-icon-${n.severity}`}>
                        <SevIcon size={16} />
                      </div>
                      <div className="notification-content">
                        <div className="notification-title">{n.title}</div>
                        <div className="notification-message">{n.message}</div>
                      </div>
                      <button
                        className="btn-icon notification-dismiss"
                        onClick={(e) => { e.stopPropagation(); handleDismiss(n.id); }}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Priority Breakdown */}
          <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.15s'}}>
            <h2 className="section-heading"><TrendingUp size={13} /> Priority Breakdown</h2>
            <div className="priority-chart glass-card">
              {['critical', 'high', 'normal', 'low'].map(p => {
                const count = data.priority_breakdown[p] || 0;
                const pct = Math.round((count / totalPriority) * 100);
                return (
                  <div key={p} className="priority-bar-row">
                    <span className="priority-bar-label">{p}</span>
                    <div className="priority-bar-track">
                      <div
                        className="priority-bar-fill"
                        style={{
                          width: `${pct}%`,
                          background: PRIORITY_COLORS[p],
                        }}
                      />
                    </div>
                    <span className="priority-bar-count">{count}</span>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Recent Activity */}
          {data.recent_activity.length > 0 && (
            <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.2s'}}>
              <h2 className="section-heading"><Clock size={13} /> Recent Activity</h2>
              <div className="activity-list glass-card">
                {data.recent_activity.map((a) => (
                  <div key={a.id} className="activity-item">
                    <div className="activity-dot" />
                    <div className="activity-detail">{a.detail}</div>
                    <div className="activity-time">
                      {new Date(a.timestamp).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* ---- Right Column ---- */}
        <div className="dashboard-col-side">
          {/* Upcoming Events */}
          <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.1s'}}>
            <div className="section-heading-row">
              <h2 className="section-heading"><CalendarDays size={13} /> Upcoming Events</h2>
              <button className="btn-link" onClick={() => navigate('/calendar')}>View all</button>
            </div>
            <div className="events-list">
              {data.upcoming_events.length === 0 && (
                <div className="events-empty">No upcoming events</div>
              )}
              {data.upcoming_events.map((ev) => (
                <div key={ev.id} className="event-card glass-card" onClick={() => navigate('/calendar')}>
                  <div className="event-color-bar" style={{ background: ev.color || '#6366f1' }} />
                  <div className="event-card-body">
                    <div className="event-card-title">{ev.title}</div>
                    <div className="event-card-time">
                      <Clock size={12} />
                      {new Date(ev.start).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}
                      {!ev.is_all_day && ` · ${new Date(ev.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
                    </div>
                    {ev.attendees?.length > 0 && (
                      <div className="event-card-attendees">
                        {ev.attendees.slice(0, 3).map((a, i) => (
                          <span key={i} className="event-attendee-chip">{a.split('@')[0]}</span>
                        ))}
                        {ev.attendees.length > 3 && <span className="event-attendee-more">+{ev.attendees.length - 3}</span>}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ---- Pending Action Items Feed ---- */}
          <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.15s'}}>
            <div className="section-heading-row">
              <h2 className="section-heading"><ListChecks size={13} /> Action Items</h2>
              <span className="section-badge">{pendingActions.length} pending</span>
            </div>
            <div className="action-feed glass-card">
              {/* Progress Bar */}
              {totalActions > 0 && (
                <div className="action-progress-bar" style={{padding: '12px 16px 4px'}}>
                  <div className="action-progress-track">
                    <div className="action-progress-fill" style={{width: `${progressPct}%`}} />
                  </div>
                  <span className="action-progress-label">{completedCount}/{totalActions} done</span>
                </div>
              )}

              {actionsLoading ? (
                <div className="action-feed-loading">Loading action items...</div>
              ) : pendingActions.length === 0 ? (
                <div className="action-feed-empty-celebration">
                  <div className="celebration-icon">🎉</div>
                  <div className="celebration-text">All caught up!</div>
                  <div className="celebration-sub">No pending action items</div>
                </div>
              ) : (
                pendingActions.slice(0, 8).map(item => (
                  <div key={item.id} className={`action-feed-item action-priority-${item.priority || 'normal'}`}>
                    <div className="action-feed-item-content">
                      <span className="action-feed-desc">{item.description}</span>
                      <div style={{display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap'}}>
                        {item.is_overdue && (
                          <span className="action-overdue-badge">
                            <AlertCircle size={10} /> Overdue
                            {item.hours_overdue > 0 && ` · ${item.hours_overdue}h`}
                          </span>
                        )}
                        {item.due_date && !item.is_overdue && (
                          <span className="action-feed-due">
                            <Clock size={10} /> {new Date(item.due_date).toLocaleDateString()}
                          </span>
                        )}
                        {item.source_subject && (
                          <a className="action-feed-source"
                            onClick={(e) => { e.stopPropagation(); navigate(`/inbox?email=${encodeURIComponent(item.email_id)}`); }}>
                            <Mail size={10} /> {item.source_subject.slice(0, 30)}
                          </a>
                        )}
                      </div>
                    </div>
                    <div className="action-feed-btns">
                      <button className="action-feed-btn done" title="Complete"
                        onClick={() => handleActionUpdate(item.id, 'completed')}>
                        <CheckCircle size={14} />
                      </button>
                      <button className="action-feed-btn dismiss" title="Dismiss"
                        onClick={() => handleActionUpdate(item.id, 'dismissed')}>
                        <XCircle size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          {/* Microsoft Graph Integration */}
          <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.2s'}}>
            <div className="integration-card glass-card">
              <div className="integration-header">
                <div className="integration-icon">
                  <Link2 size={20} />
                </div>
                <div>
                  <div className="integration-title">Microsoft Graph</div>
                  {graphStatus && (
                    <span className="integration-badge" style={{
                      background: graphStatus.mode === "live" ? "#22c55e22" : (graphStatus.mode === "offline" || graphStatus.mode === "error" ? "rgba(244, 63, 94, 0.1)" : "#f9731622"), 
                      color: graphStatus.mode === "live" ? "#22c55e" : (graphStatus.mode === "offline" ? "Disconnected" : (graphStatus.mode === "error" ? "Error" : "Mock Mode"))
                    }}>
                      {graphStatus.mode === "live" ? "Live" : (graphStatus.mode === "offline" ? "Disconnected" : (graphStatus.mode === "error" ? "Error" : "Mock Mode"))}
                    </span>
                  )}
                </div>
              </div>
              <p className="integration-desc">
                {graphStatus?.user_email && graphStatus.user_email !== "Unknown"
                  ? `Connected as ${graphStatus.user_email}` 
                  : 'Connect Microsoft Graph to sync Outlook emails, Teams notifications, and SharePoint documents.'}
              </p>
              <div className="integration-features">
                <div className="integration-feature"><ShieldCheck size={13} /> Outlook Sync</div>
                <div className="integration-feature"><Bell size={13} /> Teams Alerts</div>
                <div className="integration-feature"><CalendarDays size={13} /> Calendar Sync</div>
              </div>
              <button className="btn btn-secondary" onClick={() => navigate('/settings')} style={{width: "100%", marginTop: 12}}>Manage Connection</button>
            </div>
          </section>

          {/* Accounts */}
          <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.25s'}}>
            <h2 className="section-heading">Accounts</h2>
            <div className="accounts-list">
              {data.accounts.map((acc) => (
                <div key={acc.id} className="account-row glass-card">
                  <div className="account-avatar" style={{ background: acc.color }}>
                    {acc.name.charAt(0)}
                  </div>
                  <div className="account-info">
                    <div className="account-name">{acc.name}</div>
                    <div className="account-email">
                      {acc.email} · {acc.email_count || 0} emails
                    </div>
                  </div>
                  <div className={`account-status ${acc.is_active ? 'active' : ''}`} />
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
