import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mail, MailWarning, CheckCircle2, Star,
  AlertTriangle, Bell, Clock, CalendarDays,
  ArrowRight, Sparkles, Link2, ShieldCheck,
  TrendingUp, Zap, X, ExternalLink, Eye,
  Plane, CreditCard, GitPullRequest, ClipboardList,
  ShieldAlert, Newspaper, Users, Activity
} from 'lucide-react';
import { fetchDashboard, dismissNotification } from '../api';
import { SmartCard } from '../components/SmartCard';
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

/* ── Rich Notification Card ─────────────────────────────────────────────── */
function NotificationCard({ n, onDismiss, onNavigate }) {
  const SevIcon = SEVERITY_ICONS[n.severity] || Bell;

  const iconClass = {
    critical: 'notif-card-icon--critical',
    warning:  'notif-card-icon--warning',
    info:     'notif-card-icon--info',
  }[n.severity] || 'notif-card-icon--info';

  const cardClass = {
    critical: 'notification-card-rich--critical',
    warning:  'notification-card-rich--warning',
    info:     'notification-card-rich--info',
  }[n.severity] || 'notification-card-rich--info';

  const primaryBtnClass = {
    critical: 'notif-action-btn--critical',
    warning:  'notif-action-btn--warn',
    info:     'notif-action-btn--primary',
  }[n.severity] || 'notif-action-btn--primary';

  const actionLabel = n.related_type === 'email'
    ? 'View Email'
    : n.related_type === 'event'
    ? 'View Event'
    : 'View Details';

  return (
    <div className={`notification-card-rich ${cardClass}`} onClick={onNavigate}>
      <div className="notif-card-header">
        <div className={`notif-card-icon ${iconClass}`}>
          <SevIcon size={18} />
        </div>
        <div className="notif-card-body">
          <div className="notif-card-title">{n.title}</div>
          <div className="notif-card-message">{n.message}</div>
        </div>
        <button
          className="notif-card-dismiss"
          onClick={(e) => { e.stopPropagation(); onDismiss(n.id); }}
        >
          <X size={13} />
        </button>
      </div>
      <div className="notif-card-actions">
        <button className={`notif-action-btn ${primaryBtnClass}`} onClick={onNavigate}>
          <Eye size={11} /> {actionLabel} →
        </button>
        <button
          className="notif-action-btn notif-action-btn--ghost"
          onClick={(e) => { e.stopPropagation(); onDismiss(n.id); }}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

function Dashboard() {
  const [data, setData] = useState(null);
  const [graphStatus, setGraphStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetch("/api/graph/status").then(r => r.json()).then(j => setGraphStatus(j)).catch(() => {});
  }, []);

  useEffect(() => {
    loadDashboard();
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

          {/* AI Alerts — Rich Cards (max 3 shown) */}
          {data.notifications.length > 0 && (
            <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.1s'}}>
              <div className="section-heading-row">
                <h2 className="section-heading"><Zap size={13} /> AI Alerts &amp; Notifications</h2>
                {data.notifications.length > 3 && (
                  <span className="section-count-badge">{data.notifications.length} total</span>
                )}
              </div>
              <div className="notification-list">
                {data.notifications.slice(0, 3).map((n) => (
                  <NotificationCard
                    key={n.id}
                    n={n}
                    onDismiss={handleDismiss}
                    onNavigate={() => {
                      if (n.related_type === 'email' && n.related_id) {
                        navigate(`/inbox?email=${n.related_id}`);
                      } else if (n.related_type === 'email') {
                        navigate('/inbox');
                      } else if (n.related_type === 'event') {
                        navigate('/calendar');
                      }
                    }}
                  />
                ))}
              </div>
            </section>
          )}

          {/* AI Priority Deck — Smart Cards (max 4 shown) */}
          {data.recent_emails && data.recent_emails.length > 0 && (
            <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.12s'}}>
              <div className="section-heading-row">
                <h2 className="section-heading"><Sparkles size={13} /> Intelligent Priority Deck</h2>
                <button className="btn-link" onClick={() => navigate('/inbox')}>View all <ArrowRight size={12} /></button>
              </div>
              <div className="smart-cards-list">
                {data.recent_emails.slice(0, 4).map(email => (
                  <SmartCard
                    key={email.id}
                    email={email}
                    onNavigate={() => navigate(`/inbox?email=${email.id}`)}
                  />
                ))}
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

          {/* Microsoft Graph Integration */}
          <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.2s'}}>
            <div className="ms-graph-card glass-card">
              <div className="ms-graph-header">
                {/* Microsoft logo squares */}
                <div className="ms-logo">
                  <div className="ms-logo-grid">
                    <div style={{background:'#f25022'}} />
                    <div style={{background:'#7fba00'}} />
                    <div style={{background:'#00a4ef'}} />
                    <div style={{background:'#ffb900'}} />
                  </div>
                </div>
                <div>
                  <div className="ms-graph-title">Microsoft Graph</div>
                  <span
                    className="ms-graph-badge"
                    style={{
                      background: graphStatus?.mode === 'live' ? 'rgba(34,197,94,0.15)' : 'rgba(249,115,22,0.15)',
                      color: graphStatus?.mode === 'live' ? '#4ade80' : '#fb923c',
                    }}
                  >
                    {graphStatus?.mode === 'live' ? 'Live' : 'Mock Mode'}
                  </span>
                </div>
              </div>

              <p className="ms-graph-desc">
                {graphStatus?.user_email && graphStatus.user_email !== 'Unknown'
                  ? `Connected as ${graphStatus.user_email}`
                  : 'Connect your Microsoft account to sync Outlook emails, Teams alerts, and calendar events in real-time.'}
              </p>

              <div className="ms-graph-features">
                <div className="ms-graph-feature">
                  <div className="ms-feature-icon" style={{background:'rgba(0,164,239,0.15)',color:'#38bdf8'}}><Mail size={13}/></div>
                  <span>Outlook Mail Sync</span>
                </div>
                <div className="ms-graph-feature">
                  <div className="ms-feature-icon" style={{background:'rgba(91,33,182,0.15)',color:'#a78bfa'}}><Users size={13}/></div>
                  <span>Teams Notifications</span>
                </div>
                <div className="ms-graph-feature">
                  <div className="ms-feature-icon" style={{background:'rgba(16,185,129,0.15)',color:'#34d399'}}><CalendarDays size={13}/></div>
                  <span>Calendar Events</span>
                </div>
                <div className="ms-graph-feature">
                  <div className="ms-feature-icon" style={{background:'rgba(245,158,11,0.15)',color:'#fbbf24'}}><Activity size={13}/></div>
                  <span>Activity Feed</span>
                </div>
              </div>

              <div style={{display:'flex', gap:8, marginTop:4}}>
                <button className="btn btn-secondary" onClick={() => navigate('/outlook')} style={{flex:1}}>
                  <ExternalLink size={13}/> Open Graph
                </button>
                <button className="btn btn-primary" onClick={() => navigate('/settings')} style={{flex:1}}>
                  <ShieldCheck size={13}/> Connect
                </button>
              </div>
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
