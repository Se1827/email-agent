import { useState, useEffect } from 'react';
import {
  Settings, Shield, Database, Activity, Link2,
  Server, Eye, Lock, Wifi, WifiOff, ExternalLink
} from 'lucide-react';
import { fetchAccounts, fetchStorageStats } from '../api';
import './SettingsPage.css';

function SettingsPage() {
  const [accounts, setAccounts] = useState([]);
  const [storage, setStorage] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchAccounts().catch(() => []),
      fetchStorageStats().catch(() => null),
    ]).then(([acc, stor]) => {
      setAccounts(acc);
      setStorage(stor);
      setLoading(false);
    });
  }, []);

  return (
    <div className="settings-page" id="settings-page">
      <div className="settings-header animate-fade-in">
        <h1 className="settings-title"><Settings size={24} /> Settings</h1>
        <p className="settings-subtitle">Configure accounts, privacy, and integrations</p>
      </div>

      <div className="settings-grid">
        {/* Accounts */}
        <section className="settings-card glass-card animate-slide-up">
          <div className="settings-card-header">
            <Server size={18} />
            <h2>Email Accounts</h2>
          </div>
          <p className="settings-card-desc">
            Configured IMAP accounts. Add accounts by editing <code>data/accounts.json</code>.
          </p>
          <div className="settings-accounts-list">
            {accounts.map((acc) => (
              <div key={acc.id} className="settings-account-row">
                <div className="settings-account-avatar" style={{ background: acc.color }}>
                  {acc.name.charAt(0)}
                </div>
                <div className="settings-account-info">
                  <div className="settings-account-name">{acc.name}</div>
                  <div className="settings-account-email">{acc.email}</div>
                </div>
                <div className="settings-account-tags">
                  <span className="settings-tag">{acc.provider}</span>
                  {acc.is_active ? (
                    <span className="settings-tag settings-tag-active"><Wifi size={10} /> Active</span>
                  ) : (
                    <span className="settings-tag settings-tag-inactive"><WifiOff size={10} /> Inactive</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* PII Protection */}
        <section className="settings-card glass-card animate-slide-up" style={{animationDelay: '0.05s'}}>
          <div className="settings-card-header">
            <Shield size={18} />
            <h2>PII Protection</h2>
          </div>
          <p className="settings-card-desc">
            All email content is processed through the PII Gateway before reaching the LLM. Sensitive data (SSNs, credit cards, phone numbers, names) is replaced with semantic tokens.
          </p>
          <div className="pii-modes">
            <div className="pii-mode active">
              <div className="pii-mode-header">
                <Lock size={14} />
                <strong>Strict Presidio</strong>
                <span className="pii-mode-badge">Active</span>
              </div>
              <p>Full NLP + regex detection. Slowest but most thorough.</p>
            </div>
            <div className="pii-mode">
              <div className="pii-mode-header">
                <Eye size={14} />
                <strong>Lazy Semantic</strong>
              </div>
              <p>NLP only when sensitive context detected. Good balance.</p>
            </div>
            <div className="pii-mode">
              <div className="pii-mode-header">
                <Activity size={14} />
                <strong>Regex Only</strong>
              </div>
              <p>Pattern matching only. Fastest but less thorough.</p>
            </div>
          </div>
          <p className="settings-hint">Change PII mode via <code>PII_MODE</code> in your <code>.env</code> file.</p>
        </section>

        {/* Storage */}
        <section className="settings-card glass-card animate-slide-up" style={{animationDelay: '0.1s'}}>
          <div className="settings-card-header">
            <Database size={18} />
            <h2>Encrypted Storage</h2>
          </div>
          {storage?.configured ? (
            <>
              <p className="settings-card-desc">
                PostgreSQL with Fernet encryption. All payloads encrypted at rest.
              </p>
              <div className="storage-stats">
                {Object.entries(storage.records || {}).map(([type, count]) => (
                  <div key={type} className="storage-stat-row">
                    <span className="storage-stat-type">{type.replace(/_/g, ' ')}</span>
                    <span className="storage-stat-count">{count}</span>
                  </div>
                ))}
                <div className="storage-stat-row">
                  <span className="storage-stat-type">semantic memories</span>
                  <span className="storage-stat-count">{storage.semantic_memories || 0}</span>
                </div>
              </div>
            </>
          ) : (
            <div className="storage-disabled">
              <Database size={32} />
              <p>Storage is not configured.</p>
              <p className="settings-hint">Set <code>STORAGE_ENABLED=true</code> and configure <code>DATABASE_URL</code> in your <code>.env</code>.</p>
            </div>
          )}
        </section>

        {/* Microsoft Graph */}
        <section className="settings-card glass-card animate-slide-up" style={{animationDelay: '0.15s'}}>
          <div className="settings-card-header">
            <Link2 size={18} />
            <h2>Integrations</h2>
          </div>
          <div className="integration-row">
            <div className="integration-row-icon" style={{ background: 'var(--gradient-cool)' }}>
              <ExternalLink size={18} />
            </div>
            <div className="integration-row-info">
              <div className="integration-row-name">Microsoft Graph API</div>
              <div className="integration-row-desc">Sync Outlook, Teams, and Calendar via OAuth2</div>
            </div>
            <span className="settings-tag settings-tag-soon">Coming Soon</span>
          </div>
          <div className="integration-row">
            <div className="integration-row-icon" style={{ background: 'var(--gradient-success)' }}>
              <ExternalLink size={18} />
            </div>
            <div className="integration-row-info">
              <div className="integration-row-name">Google Calendar</div>
              <div className="integration-row-desc">Sync Google Calendar events</div>
            </div>
            <span className="settings-tag settings-tag-soon">Coming Soon</span>
          </div>
        </section>

        {/* Telemetry */}
        <section className="settings-card glass-card animate-slide-up" style={{animationDelay: '0.2s'}}>
          <div className="settings-card-header">
            <Activity size={18} />
            <h2>Observability</h2>
          </div>
          <p className="settings-card-desc">
            OpenTelemetry tracing for API requests, LLM calls, and storage operations.
          </p>
          <div className="settings-hint">
            Configure via <code>OTEL_ENABLED</code>, <code>OTEL_SERVICE_NAME</code>, and <code>OTEL_EXPORTER_OTLP_ENDPOINT</code> in your <code>.env</code>.
          </div>
        </section>
      </div>
    </div>
  );
}

export default SettingsPage;
