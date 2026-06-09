import { useState, useEffect } from 'react';
import {
  Settings, Shield, Database, Activity, Link2,
  Server, Eye, Lock, Wifi, WifiOff, ExternalLink,
  Plus, Save, Trash2, X, Pencil
} from 'lucide-react';
import {
  createAccount,
  deleteAccount,
  fetchAccounts,
  fetchStorageStats,
  updateAccount,
} from '../api';
import './SettingsPage.css';

const EMPTY_ACCOUNT = {
  name: '',
  email: '',
  provider: 'imap',
  imap_host: '',
  imap_port: 993,
  imap_user: '',
  imap_pass: '',
  imap_mailbox: 'INBOX',
  imap_use_ssl: true,
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_pass: '',
  smtp_use_ssl: false,
  smtp_use_tls: true,
  color: '#3b82f6',
  is_active: true,
};

function SettingsPage() {
  const [accounts, setAccounts] = useState([]);
  const [storage, setStorage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_ACCOUNT);
  const [saving, setSaving] = useState(false);
  const [accountError, setAccountError] = useState(null);

  const loadSettings = () => {
    setLoading(true);
    return Promise.all([
      fetchAccounts().catch(() => []),
      fetchStorageStats().catch(() => null),
    ]).then(([acc, stor]) => {
      setAccounts(acc);
      setStorage(stor);
      setLoading(false);
    });
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const startCreate = () => {
    setEditingId('new');
    setForm(EMPTY_ACCOUNT);
    setAccountError(null);
  };

  const startEdit = (account) => {
    setEditingId(account.id);
    setForm({
      ...EMPTY_ACCOUNT,
      ...account,
      imap_pass: '',
    });
    setAccountError(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setForm(EMPTY_ACCOUNT);
    setAccountError(null);
  };

  const setField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setSaving(true);
    setAccountError(null);
    try {
      const payload = {
        ...form,
        imap_port: Number(form.imap_port) || 993,
        imap_user: form.imap_user || form.email,
      };
      if (editingId === 'new') {
        await createAccount(payload);
      } else {
        await updateAccount(editingId, payload);
      }
      await loadSettings();
      cancelEdit();
    } catch (err) {
      setAccountError(err.message || 'Could not save account.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (account) => {
    if (!account) return;
    setSaving(true);
    setAccountError(null);
    try {
      await deleteAccount(account.id);
      await loadSettings();
      if (editingId === account.id) cancelEdit();
    } catch (err) {
      setAccountError(err.message || 'Could not delete account.');
    } finally {
      setSaving(false);
    }
  };

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
            <button className="btn btn-secondary settings-card-action" onClick={startCreate}>
              <Plus size={14} /> Add
            </button>
          </div>
          <p className="settings-card-desc">
            Add mock or IMAP accounts here. Active accounts are loaded into the inbox and stored with separate encrypted inbox scopes.
          </p>
          {accountError && <div className="settings-error">{accountError}</div>}
          <div className="settings-accounts-list">
            {accounts.map((acc) => (
              <div key={acc.id} className="settings-account-row">
                <div className="settings-account-avatar" style={{ background: acc.color }}>
                  {acc.name.charAt(0)}
                </div>
                <div className="settings-account-info">
                  <div className="settings-account-name">{acc.name}</div>
                  <div className="settings-account-email">{acc.email}</div>
                  {acc.provider !== 'mock' && (
                    <div className="settings-account-meta">
                      {acc.imap_host || 'No host'} · {acc.imap_mailbox || 'INBOX'}
                    </div>
                  )}
                </div>
                <div className="settings-account-tags">
                  <span className="settings-tag">{acc.provider}</span>
                  {acc.is_active ? (
                    <span className="settings-tag settings-tag-active"><Wifi size={10} /> Active</span>
                  ) : (
                    <span className="settings-tag settings-tag-inactive"><WifiOff size={10} /> Inactive</span>
                  )}
                </div>
                <button className="btn-icon" onClick={() => startEdit(acc)} title="Edit account">
                  <Pencil size={14} />
                </button>
              </div>
            ))}
            {!loading && accounts.length === 0 && (
              <div className="settings-empty">No accounts configured yet.</div>
            )}
          </div>

          {editingId && (
            <form className="account-editor" onSubmit={handleSave}>
              <div className="account-editor-header">
                <strong>{editingId === 'new' ? 'Add account' : 'Edit account'}</strong>
                <button type="button" className="btn-icon" onClick={cancelEdit}>
                  <X size={14} />
                </button>
              </div>
              <div className="account-form-grid">
                <label>
                  Name
                  <input className="input" value={form.name} onChange={(e) => setField('name', e.target.value)} required />
                </label>
                <label>
                  Email
                  <input className="input" type="email" value={form.email} onChange={(e) => setField('email', e.target.value)} required />
                </label>
                <label>
                  Provider
                  <select className="select" value={form.provider} onChange={(e) => setField('provider', e.target.value)}>
                    <option value="imap">IMAP</option>
                    <option value="gmail">Gmail IMAP</option>
                    <option value="outlook">Outlook IMAP</option>
                    <option value="mock">Mock</option>
                  </select>
                </label>
                <label>
                  Color
                  <input className="input" type="color" value={form.color} onChange={(e) => setField('color', e.target.value)} />
                </label>
                {form.provider !== 'mock' && (
                  <>
                    <label>
                      IMAP host
                      <input className="input" value={form.imap_host} onChange={(e) => setField('imap_host', e.target.value)} placeholder="imap.gmail.com" />
                    </label>
                    <label>
                      Port
                      <input className="input" type="number" value={form.imap_port} onChange={(e) => setField('imap_port', e.target.value)} />
                    </label>
                    <label>
                      Username
                      <input className="input" value={form.imap_user} onChange={(e) => setField('imap_user', e.target.value)} placeholder={form.email} />
                    </label>
                    <label>
                      Password
                      <input className="input" type="password" value={form.imap_pass} onChange={(e) => setField('imap_pass', e.target.value)} placeholder={editingId === 'new' ? 'App password' : 'Leave blank to keep existing'} />
                    </label>
                    <label>
                      Mailbox
                      <input className="input" value={form.imap_mailbox} onChange={(e) => setField('imap_mailbox', e.target.value)} />
                    </label>
                    <label className="checkbox-row">
                      <input type="checkbox" checked={form.imap_use_ssl} onChange={(e) => setField('imap_use_ssl', e.target.checked)} />
                      Use SSL
                    </label>
                    <div className="account-form-divider">
                      <span className="account-form-divider-text">SMTP (Outgoing)</span>
                    </div>
                    <label>
                      SMTP Host
                      <div className="input-with-action">
                        <input className="input" value={form.smtp_host} onChange={(e) => setField('smtp_host', e.target.value)} placeholder="smtp.gmail.com" />
                        <button type="button" className="btn-link" onClick={() => setField('smtp_host', form.imap_host)} title="Copy from IMAP host">Same as IMAP</button>
                      </div>
                    </label>
                    <label>
                      SMTP Port
                      <input className="input" type="number" value={form.smtp_port} onChange={(e) => setField('smtp_port', e.target.value)} />
                    </label>
                    <label>
                      SMTP Username
                      <input className="input" value={form.smtp_user} onChange={(e) => setField('smtp_user', e.target.value)} placeholder={form.imap_user || form.email || 'Same as IMAP'} />
                    </label>
                    <label>
                      SMTP Password
                      <input className="input" type="password" value={form.smtp_pass} onChange={(e) => setField('smtp_pass', e.target.value)} placeholder={form.imap_pass ? 'Same as IMAP' : 'App password'} />
                    </label>
                    <label className="checkbox-row">
                      <input type="checkbox" checked={form.smtp_use_ssl} onChange={(e) => { setField('smtp_use_ssl', e.target.checked); if (e.target.checked) setField('smtp_use_tls', false); }} />
                      SMTP SSL (port 465)
                    </label>
                    <label className="checkbox-row">
                      <input type="checkbox" checked={form.smtp_use_tls} onChange={(e) => { setField('smtp_use_tls', e.target.checked); if (e.target.checked) setField('smtp_use_ssl', false); }} />
                      SMTP STARTTLS (port 587)
                    </label>
                  </>
                )}
                <label className="checkbox-row">
                  <input type="checkbox" checked={form.is_active} onChange={(e) => setField('is_active', e.target.checked)} />
                  Active in inbox
                </label>
              </div>
              <div className="account-editor-actions">
                {editingId !== 'new' && (
                  <button type="button" className="btn btn-secondary" onClick={() => handleDelete(accounts.find((a) => a.id === editingId))} disabled={saving}>
                    <Trash2 size={14} /> Delete
                  </button>
                )}
                <button className="btn btn-primary" disabled={saving}>
                  <Save size={14} /> {saving ? 'Saving...' : 'Save account'}
                </button>
              </div>
            </form>
          )}
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
