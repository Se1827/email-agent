import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mail, MailWarning, CheckCircle2, Star,
  AlertTriangle, Bell, Clock, CalendarDays,
  ArrowRight, Sparkles, Link2, ShieldCheck,
  TrendingUp, Zap, X
} from 'lucide-react';
import { fetchDashboard, dismissNotification } from '../api';
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

function Dashboard() {
  const [data, setData] = useState(null);
  const [graphStatus, setGraphStatus] = useState(null);
  const [graphLoading, setGraphLoading] = useState(false);

  useEffect(() => {
    fetch("/api/graph/graph/status").then(r => r.json()).then(j => setGraphStatus(j)).catch(() => {});
  }, []);

  const [loading, setLoading] = useState(true);
  const connectGraph = async () => {
    setGraphLoading(true);
    try {
      const res = await fetch("/api/graph/graph/status");
      const json = await res.json();
      setGraphStatus(json);
      alert("Connected! Mode: " + json.mode);
    } catch (e) {
      alert("Failed: " + e.message);
    } finally {
      setGraphLoading(false);
    }
  };
  const navigate = useNavigate();

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

          {/* Microsoft Graph Placeholder */}
          <section className="dashboard-section animate-slide-up" style={{animationDelay: '0.2s'}}>
            <div className="integration-card glass-card">
              <div className="integration-header">
                <div className="integration-icon">
                  <Link2 size={20} />
                </div>
                <div>
                  <div className="integration-title">Microsoft 365</div>
                  <span className="integration-badge" style={{background: graphStatus?.mode === "live" ? "#22c55e22" : "#f9731622", color: graphStatus?.mode === "live" ? "#22c55e" : "#f97316"}}>{graphStatus?.mode === "live" ? "Live" : "Mock Mode"}</span>
                </div>
              </div>
              <p className="integration-desc">
                Connect Microsoft Graph to sync Outlook emails, Teams notifications, and SharePoint documents.
              </p>
              <div className="integration-features">
                <div className="integration-feature"><ShieldCheck size={13} /> Outlook Sync</div>
                <div className="integration-feature"><Bell size={13} /> Teams Alerts</div>
                <div className="integration-feature"><CalendarDays size={13} /> Calendar Sync</div>
              </div>
              <button className="btn btn-primary" onClick={connectGraph} style={{width: "100%", marginTop: 12}}>Connect Microsoft 365</button>
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


