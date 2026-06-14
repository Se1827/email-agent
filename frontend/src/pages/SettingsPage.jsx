import { useState, useEffect, useRef } from 'react';
import {
  Settings, Server, Shield, Database, Link2, Cpu,
  Eye, EyeOff, Lock, Activity, Plus, Save, Trash2,
  X, Pencil, Check, RefreshCw, ExternalLink, Copy,
  ChevronRight, AlertTriangle, CheckCircle, WifiOff,
  Wifi, Loader, Info, Zap, Brain, ListChecks, Sparkles
} from 'lucide-react';
import {
  createAccount, deleteAccount, fetchAccounts, fetchStorageStats,
  updateAccount, fetchGraphConfig, updateGraphConfig,
  fetchSettings, saveSettings,
  fetchStorageSetupStatus, setupStorage,
  triggerGraphLogin, fetchGraphLoginStatus,
  fetchAIMode, updateAIMode, fetchPreferences,
  createPreference, deletePreference,
} from '../api';
import './SettingsPage.css';

// ── Provider presets ─────────────────────────────────────────────────────────
const PROVIDER_PRESETS = {
  gmail: { imap_host: 'imap.gmail.com', imap_port: 993, imap_use_ssl: true, smtp_host: 'smtp.gmail.com', smtp_port: 587, smtp_use_ssl: false, smtp_use_tls: true },
  outlook: { imap_host: 'outlook.office365.com', imap_port: 993, imap_use_ssl: true, smtp_host: 'smtp.office365.com', smtp_port: 587, smtp_use_ssl: false, smtp_use_tls: true },
  yahoo: { imap_host: 'imap.mail.yahoo.com', imap_port: 993, imap_use_ssl: true, smtp_host: 'smtp.mail.yahoo.com', smtp_port: 587, smtp_use_ssl: false, smtp_use_tls: true },
  imap: { imap_host: '', imap_port: 993, imap_use_ssl: true, smtp_host: '', smtp_port: 587, smtp_use_ssl: false, smtp_use_tls: true },
  mock: { imap_host: '', imap_port: 0, imap_use_ssl: false, smtp_host: '', smtp_port: 0, smtp_use_ssl: false, smtp_use_tls: false },
};

const EMPTY_ACCOUNT = {
  name: '', email: '', provider: 'gmail',
  imap_host: 'imap.gmail.com', imap_port: 993, imap_user: '', imap_pass: '',
  imap_mailbox: 'INBOX', imap_use_ssl: true,
  smtp_host: 'smtp.gmail.com', smtp_port: 587, smtp_user: '', smtp_pass: '',
  smtp_use_ssl: false, smtp_use_tls: true,
  color: '#6366f1', is_active: true,
};

const TABS = [
  { id: 'accounts', label: 'Accounts', icon: Server },
  { id: 'ai', label: 'AI & LLM', icon: Cpu },
  { id: 'graph', label: 'Microsoft Graph', icon: Link2 },
  { id: 'privacy', label: 'Privacy', icon: Shield },
  { id: 'storage', label: 'Storage & DB', icon: Database },
];

const PII_MODES = [
  { id: 'strict_presidio', label: 'Strict (Presidio)', icon: Lock, desc: 'Full NLP + regex. Catches names, orgs, locations. Safest.' },
  { id: 'lazy_semantic', label: 'Lazy Semantic', icon: Eye, desc: 'Presidio only when sensitive context is detected. Balanced.' },
  { id: 'regex_only', label: 'Regex Only', icon: Zap, desc: 'Pattern matching only. Fastest. Misses semantic PII.' },
];

const MODELS = [
  'llama-3.3-70b-versatile',
  'llama-3.1-70b-versatile',
  'llama-3.1-8b-instant',
  'mixtral-8x7b-32768',
];

const COLORS = ['#6366f1', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6'];

// ── Toast ────────────────────────────────────────────────────────────────────
function Toast({ message, type = 'success', onDone }) {
  useEffect(() => { const t = setTimeout(onDone, 2800); return () => clearTimeout(t); }, [onDone]);
  return <div className={`settings-toast settings-toast--${type}`}>{type === 'success' ? <Check size={14} /> : <AlertTriangle size={14} />}{message}</div>;
}

// ── Main Component ───────────────────────────────────────────────────────────
function SettingsPage() {
  const [tab, setTab] = useState('accounts');
  const [toast, setToast] = useState(null);

  const showToast = (msg, type = 'success') => setToast({ msg, type });

  const handleAIModeSwitch = async (newMode, setAiMode) => {
    try {
      const result = await updateAIMode(newMode);
      setAiMode(result.ai_mode);
      showToast(`Switched to ${result.ai_mode === 'ai_rich' ? 'AI-Rich' : 'Classic'} mode.`);
    } catch (err) {
      showToast(err.message || 'Could not switch AI mode.', 'error');
    }
  };

  return (
    <div className="settings-page" id="settings-page">
      <div className="settings-header animate-fade-in">
        <h1 className="settings-title"><Settings size={24} /> Settings</h1>
        <p className="settings-subtitle">Configure everything from here — no .env editing needed</p>
      </div>

      <div className="settings-layout">
        {/* Left tab nav */}
        <nav className="settings-nav">
          {TABS.map(t => (
            <button key={t.id} className={`settings-nav-item ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              <t.icon size={16} /> {t.label}
              {tab === t.id && <ChevronRight size={14} className="settings-nav-chevron" />}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div className="settings-content">
          {tab === 'accounts' && <AccountsTab showToast={showToast} />}
          {tab === 'ai' && <AITab showToast={showToast} />}
          {tab === 'graph' && <GraphTab showToast={showToast} />}
          {tab === 'privacy' && <PrivacyTab showToast={showToast} />}
          {tab === 'storage' && <StorageTab showToast={showToast} />}
        </div>
      </div>

      {toast && <Toast message={toast.msg} type={toast.type} onDone={() => setToast(null)} />}
    </div>
  );
}

// ══════════════════ ACCOUNTS TAB ═════════════════════════════════════════════
function AccountsTab({ showToast }) {
  const [accounts, setAccounts] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_ACCOUNT);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const load = () => fetchAccounts().catch(() => []).then(setAccounts);
  useEffect(() => { load(); }, []);

  const applyPreset = (provider) => {
    const preset = PROVIDER_PRESETS[provider] || {};
    setForm(f => ({ ...f, provider, ...preset }));
  };

  const startCreate = () => { setEditingId('new'); setForm(EMPTY_ACCOUNT); setError(null); };
  const startEdit = (acc) => { setEditingId(acc.id); setForm({ ...EMPTY_ACCOUNT, ...acc, imap_pass: '', smtp_pass: '' }); setError(null); };
  const cancel = () => { setEditingId(null); setError(null); };
  const setF = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const save = async (e) => {
    e.preventDefault(); setSaving(true); setError(null);
    try {
      const p = { ...form, imap_port: +form.imap_port || 993, smtp_port: +form.smtp_port || 587, imap_user: form.imap_user || form.email, smtp_user: form.smtp_user || form.email };
      editingId === 'new' ? await createAccount(p) : await updateAccount(editingId, p);
      await load(); cancel(); showToast('Account saved.');
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  };

  const del = async (acc) => {
    setSaving(true);
    try { await deleteAccount(acc.id); await load(); if (editingId === acc.id) cancel(); showToast('Account removed.'); }
    catch (err) { setError(err.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="stab">
      <div className="stab-header">
        <div><h2>Email Accounts</h2><p>IMAP accounts for reading + SMTP for sending.</p></div>
        <button className="btn btn-primary" onClick={startCreate}><Plus size={14} /> Add Account</button>
      </div>

      {error && <div className="s-error"><AlertTriangle size={14} />{error}</div>}

      <div className="account-list">
        {accounts.map(acc => (
          <div key={acc.id} className={`account-card ${!acc.is_active ? 'inactive' : ''} ${editingId === acc.id ? 'editing' : ''}`}>
            <div className="account-card-avatar" style={{ background: acc.color }}>{acc.name.charAt(0).toUpperCase()}</div>
            <div className="account-card-info">
              <div className="account-card-name">{acc.name}{!acc.is_active && <span className="s-badge s-badge--off">Disabled</span>}</div>
              <div className="account-card-email">{acc.email} · {acc.provider}</div>
            </div>
            <div className="account-card-actions">
              <button className="btn-icon" onClick={() => startEdit(acc)} title="Edit"><Pencil size={14} /></button>
              <button className="btn-icon danger" onClick={() => del(acc)} title="Delete"><Trash2 size={14} /></button>
            </div>
          </div>
        ))}
        {accounts.length === 0 && <div className="s-empty"><Server size={32} /><p>No accounts yet. Add one to connect your inbox.</p></div>}
      </div>

      {editingId && (
        <form className="account-editor" onSubmit={save}>
          <div className="account-editor-title">
            <strong>{editingId === 'new' ? 'Add Account' : 'Edit Account'}</strong>
            <button type="button" className="btn-icon" onClick={cancel}><X size={14} /></button>
          </div>

          {/* Provider presets */}
          <div className="provider-presets">
            {['gmail', 'outlook', 'yahoo', 'imap', 'mock'].map(p => (
              <button key={p} type="button" className={`preset-btn ${form.provider === p ? 'active' : ''}`} onClick={() => applyPreset(p)}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>

          <div className="form-grid">
            <label className="form-field"><span>Display name</span><input className="input" value={form.name} onChange={e => setF('name', e.target.value)} required placeholder="Work Gmail" /></label>
            <label className="form-field"><span>Email address</span><input className="input" type="email" value={form.email} onChange={e => setF('email', e.target.value)} required placeholder="you@gmail.com" /></label>

            <label className="form-field"><span>Color tag</span>
              <div className="color-row">
                {COLORS.map(c => <button key={c} type="button" className={`color-swatch ${form.color === c ? 'active' : ''}`} style={{ background: c }} onClick={() => setF('color', c)} />)}
              </div>
            </label>
            <label className="form-field form-checkbox-row"><input type="checkbox" checked={form.is_active} onChange={e => setF('is_active', e.target.checked)} /><span>Active in inbox</span></label>

            {form.provider !== 'mock' && <>
              <div className="form-section-label">IMAP — Incoming Mail</div>
              <label className="form-field"><span>IMAP host</span><input className="input" value={form.imap_host} onChange={e => setF('imap_host', e.target.value)} placeholder="imap.gmail.com" /></label>
              <label className="form-field"><span>Port</span><input className="input" type="number" value={form.imap_port} onChange={e => setF('imap_port', e.target.value)} /></label>
              <label className="form-field"><span>Username</span><input className="input" value={form.imap_user} onChange={e => setF('imap_user', e.target.value)} placeholder={form.email || 'Same as email'} /></label>
              <label className="form-field"><span>Password / App password</span><input className="input" type="password" value={form.imap_pass} onChange={e => setF('imap_pass', e.target.value)} placeholder={editingId === 'new' ? 'App password' : 'Leave blank to keep existing'} /></label>
              <label className="form-field"><span>Mailbox</span><input className="input" value={form.imap_mailbox} onChange={e => setF('imap_mailbox', e.target.value)} /></label>
              <label className="form-field form-checkbox-row"><input type="checkbox" checked={form.imap_use_ssl} onChange={e => setF('imap_use_ssl', e.target.checked)} /><span>Use SSL (port 993)</span></label>

              <div className="form-section-label">SMTP — Outgoing Mail</div>
              <label className="form-field">
                <span>SMTP host</span>
                <div className="input-with-hint">
                  <input className="input" value={form.smtp_host} onChange={e => setF('smtp_host', e.target.value)} placeholder="smtp.gmail.com" />
                  {form.imap_host && <button type="button" className="btn-link" onClick={() => setF('smtp_host', form.imap_host.replace('imap.', 'smtp.'))}>Auto-fill from IMAP</button>}
                </div>
              </label>
              <label className="form-field"><span>SMTP port</span><input className="input" type="number" value={form.smtp_port} onChange={e => setF('smtp_port', e.target.value)} /></label>
              <label className="form-field"><span>SMTP username</span><input className="input" value={form.smtp_user} onChange={e => setF('smtp_user', e.target.value)} placeholder={form.imap_user || form.email || 'Same as IMAP'} /></label>
              <label className="form-field"><span>SMTP password</span><input className="input" type="password" value={form.smtp_pass} onChange={e => setF('smtp_pass', e.target.value)} placeholder="Same as IMAP password" /></label>
              <label className="form-field form-checkbox-row"><input type="checkbox" checked={form.smtp_use_tls} onChange={e => { setF('smtp_use_tls', e.target.checked); if (e.target.checked) setF('smtp_use_ssl', false); }} /><span>STARTTLS (port 587 — recommended)</span></label>
              <label className="form-field form-checkbox-row"><input type="checkbox" checked={form.smtp_use_ssl} onChange={e => { setF('smtp_use_ssl', e.target.checked); if (e.target.checked) setF('smtp_use_tls', false); }} /><span>Direct SSL (port 465)</span></label>
            </>}
          </div>

          <div className="editor-actions">
            {editingId !== 'new' && <button type="button" className="btn btn-danger" onClick={() => del(accounts.find(a => a.id === editingId))} disabled={saving}><Trash2 size={14} /> Delete</button>}
            <button type="submit" className="btn btn-primary" disabled={saving}><Save size={14} /> {saving ? 'Saving…' : 'Save Account'}</button>
          </div>
        </form>
      )}
    </div>
  );
}

// ══════════════════ AI & LLM TAB ═════════════════════════════════════════════
function AITab({ showToast }) {
  const [s, setS] = useState(null);
  const [showKey, setShowKey] = useState(false);
  const [keyInput, setKeyInput] = useState('');
  const [saving, setSaving] = useState(false);

  // Dual AI Mode additions
  const [aiMode, setAiMode] = useState(null);
  const [aiModeOptions, setAiModeOptions] = useState([]);
  const [switchingMode, setSwitchingMode] = useState(false);

  // Preferences state
  const [preferences, setPreferences] = useState([]);
  const [newPref, setNewPref] = useState({ pref_type: 'scheduling', pref_key: '', pref_value: '' });
  const [showAddPref, setShowAddPref] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchSettings(),
      fetchAIMode(),
      fetchPreferences()
    ]).then(([settings, aiModeData, prefs]) => {
      setS(settings);
      setKeyInput('');
      if (aiModeData) {
        setAiMode(aiModeData.ai_mode);
        setAiModeOptions(aiModeData.options || []);
      }
      setPreferences(Array.isArray(prefs) ? prefs : []);
    }).catch(() => { });
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const payload = { ...s };
      if (keyInput && !keyInput.includes('•')) payload.groq_api_key = keyInput;
      else delete payload.groq_api_key;
      await saveSettings(payload);
      showToast('AI settings saved.');
    } catch (e) { showToast(e.message, 'error'); }
    finally { setSaving(false); }
  };

  const handleAIModeSwitchLocal = async (newMode) => {
    if (newMode === aiMode || switchingMode) return;
    setSwitchingMode(true);
    try {
      const result = await updateAIMode(newMode);
      setAiMode(result.ai_mode);
      showToast(`Switched to ${result.ai_mode === 'ai_rich' ? 'AI-Rich' : 'Classic'} mode.`);
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setSwitchingMode(false);
    }
  };

  if (!s) return <div className="s-loading"><Loader size={20} className="spin" /> Loading…</div>;

  return (
    <div className="stab">
      <div className="stab-header">
        <div><h2>AI & LLM Configuration</h2><p>Manage Dual AI mode, API keys, and personal memory rules.</p></div>
      </div>

      {/* AI Engine Mode selector */}
      <div className="s-section">
        <div className="s-field-label">AI Engine Mode</div>
        <div className="ai-mode-selector">
          {aiModeOptions.map((opt) => (
            <button
              key={opt.value}
              className={`ai-mode-option ${aiMode === opt.value ? 'active' : ''} ${switchingMode ? 'switching' : ''}`}
              onClick={() => handleAIModeSwitchLocal(opt.value)}
              disabled={switchingMode}
            >
              <div className="ai-mode-option-icon">
                {opt.value === 'classic' ? <Zap size={18} /> : <Brain size={18} />}
              </div>
              <div className="ai-mode-option-content">
                <div className="ai-mode-option-header">
                  <strong>{opt.label}</strong>
                  <span className={`ai-mode-badge ${opt.value === 'ai_rich' ? 'ai-rich' : 'classic'}`}>{opt.badge}</span>
                </div>
                <p>{opt.description}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="s-divider" />

      {/* Personal Rules / Preferences */}
      <div className="s-section">
        <div className="s-field-label-row">
          <div className="s-field-label">Personal Rules (Memory Agent)</div>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowAddPref(!showAddPref)}>
            <Plus size={12} /> Add Rule
          </button>
        </div>
        <p className="s-hint">Personalize how the AI handles scheduling, drafting, and priority for you.</p>

        {showAddPref && (
          <form className="pref-add-form animate-slide-down" onSubmit={async (e) => {
            e.preventDefault();
            try {
              const typeMap = {
                scheduling: 'scheduling_constraint',
                drafting: 'drafting_instruction',
                vip: 'vip_rule',
                general: 'general'
              };
              const mappedType = typeMap[newPref.pref_type] || newPref.pref_type;
              const uniqueKey = `${newPref.pref_type}_${Date.now()}`;

              await createPreference(mappedType, uniqueKey, newPref.pref_value);
              setNewPref({ pref_type: 'scheduling', pref_key: '', pref_value: '' });
              setShowAddPref(false);
              const prefs = await fetchPreferences();
              setPreferences(Array.isArray(prefs) ? prefs : []);
              showToast('Rule added.');
            } catch (err) { showToast(err.message || 'Failed to add rule', 'error'); }
          }}>
            <div className="pref-form-v">
              <div className="pref-form-group">
                <label className="pref-label">Category</label>
                <select className="select pref-type-select-v" value={newPref.pref_type} onChange={e => setNewPref(p => ({ ...p, pref_type: e.target.value }))}>
                  <option value="scheduling">Scheduling</option>
                  <option value="drafting">Drafting</option>
                  <option value="vip">VIP Rules</option>
                  <option value="general">General</option>
                </select>
              </div>
              <div className="pref-form-group">
                <label className="pref-label">Rule Instruction</label>
                <input className="input pref-value-input-v" placeholder="e.g., No meetings before 10am" value={newPref.pref_value}
                  onChange={e => setNewPref(p => ({ ...p, pref_value: e.target.value }))} required />
              </div>
              <div className="pref-form-footer">
                <button type="submit" className="btn btn-primary">Save Rule</button>
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddPref(false)}>Cancel</button>
              </div>
            </div>
          </form>
        )}

        <div className="pref-list">
          {preferences.length === 0 ? (
            <div className="s-empty-small">No custom rules set yet.</div>
          ) : (
            preferences.map(p => (
              <div key={p.id} className="pref-item">
                <span className={`pref-type-badge pref-type-${p.pref_type}`}>{p.pref_type.replace('_', ' ')}</span>
                <span className="pref-value">{p.pref_value}</span>
                <button className="btn-icon danger" title="Delete"
                  onClick={async () => {
                    try {
                      await deletePreference(p.id);
                      setPreferences(prev => prev.filter(x => x.id !== p.id));
                      showToast('Rule removed.');
                    } catch (err) { showToast(err.message, 'error'); }
                  }}>
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="s-divider" />

      {/* Groq section */}
      <div className="s-section">
        <div className="s-field-label">Groq API Key{s.groq_api_key_set && <span className="s-badge s-badge--on">Set</span>}</div>
        <div className="input-with-hint">
          <input className="input" type={showKey ? 'text' : 'password'} value={keyInput || s.groq_api_key} onChange={e => setKeyInput(e.target.value)} placeholder="gsk_…" />
          <button className="btn-icon" type="button" onClick={() => setShowKey(v => !v)}>{showKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
        <p className="s-hint">Get one free at <a href="https://console.groq.com" target="_blank" rel="noreferrer">console.groq.com</a>.</p>
      </div>

      <div className="s-section">
        <div className="s-field-label">Model</div>
        <select className="select" value={s.groq_model} onChange={e => setS(v => ({ ...v, groq_model: e.target.value }))}>
          {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <p className="s-hint">llama-3.3-70b-versatile is recommended for best quality.</p>
      </div>

      <div className="s-section">
        <div className="s-field-label">Email Source</div>
        <div className="radio-group">
          {[['mock', 'Mock', 'Use built-in seeds.'], ['imap', 'IMAP', 'Fetch real emails.']].map(([val, label, desc]) => (
            <label key={val} className={`radio-card ${s.email_source === val ? 'active' : ''}`}>
              <input type="radio" name="email_source" value={val} checked={s.email_source === val} onChange={() => setS(v => ({ ...v, email_source: val }))} />
              <div><strong>{label}</strong><span>{desc}</span></div>
            </label>
          ))}
        </div>
      </div>

      <div className="editor-actions">
        <button type="button" className="btn btn-primary" onClick={save} disabled={saving}><Save size={14} /> {saving ? 'Saving…' : 'Save AI Settings'}</button>
      </div>
    </div>
  );
}

// ══════════════════ GRAPH TAB ════════════════════════════════════════════════
function GraphTab({ showToast }) {
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState(null);
  const [loginInfo, setLoginInfo] = useState(null); // {user_code, verification_uri}
  const [loginPolling, setLoginPolling] = useState(false);
  const [saving, setSaving] = useState(false);
  const pollRef = useRef(null);

  const loadAll = async () => {
    const [cfg, st] = await Promise.all([
      fetchGraphConfig().catch(() => null),
      fetch('/api/graph/status').then(r => r.json()).catch(() => null),
    ]);
    setConfig(cfg); setStatus(st);
  };
  useEffect(() => { loadAll(); return () => clearInterval(pollRef.current); }, []);

  const saveConfig = async (e) => {
    e.preventDefault(); setSaving(true);
    try { await updateGraphConfig(config); showToast('Graph settings saved.'); await loadAll(); }
    catch (e) { showToast(e.message, 'error'); }
    finally { setSaving(false); }
  };

  const startLogin = async () => {
    try {
      const data = await triggerGraphLogin();
      if (data.mode === 'mock') { showToast('Switch to live mode first.', 'error'); return; }
      setLoginInfo(data);
      setLoginPolling(true);
      pollRef.current = setInterval(async () => {
        const st = await fetchGraphLoginStatus();
        if (st.connected) {
          clearInterval(pollRef.current);
          setLoginPolling(false);
          setLoginInfo(null);
          showToast('Connected to Microsoft Graph!');
          loadAll();
        } else if (st.error) {
          clearInterval(pollRef.current);
          setLoginPolling(false);
          showToast(st.error, 'error');
        }
      }, 4000);
    } catch (e) { showToast(e.message, 'error'); }
  };

  const copyCode = () => { navigator.clipboard.writeText(loginInfo.user_code); showToast('Code copied!'); };

  const modeBadge = status?.mode === 'live' ? 'connected' : status?.mode === 'mock' ? 'mock' : 'offline';

  if (!config) return <div className="s-loading"><Loader size={20} className="spin" /> Loading…</div>;

  return (
    <div className="stab">
      <div className="stab-header">
        <div>
          <h2>Microsoft Graph</h2>
          <p>Outlook, Calendar, Contacts, Teams via OAuth2.</p>
        </div>
        {status && <span className={`s-badge s-badge--${modeBadge}`}>{modeBadge === 'connected' ? <Wifi size={12} /> : modeBadge === 'mock' ? <Info size={12} /> : <WifiOff size={12} />} {modeBadge}</span>}
      </div>

      {/* Login panel */}
      {!config.graph_mock && (
        <div className="graph-login-section">
          {loginInfo ? (
            <div className="device-code-panel">
              <div className="device-code-title"><Loader size={14} className="spin" /> Waiting for login…</div>
              <p>Go to <a href={loginInfo.verification_uri} target="_blank" rel="noreferrer" className="link">{loginInfo.verification_uri} <ExternalLink size={12} /></a> and enter this code:</p>
              <div className="device-code-box">
                <span className="device-code">{loginInfo.user_code}</span>
                <button className="btn-icon" onClick={copyCode}><Copy size={14} /></button>
              </div>
              <p className="s-hint">This page will update automatically when you complete sign-in.</p>
            </div>
          ) : (
            <button className="btn btn-primary graph-connect-btn" onClick={startLogin} disabled={loginPolling}>
              <Link2 size={14} /> {status?.mode === 'live' ? 'Re-connect Microsoft Account' : 'Connect Microsoft Account'}
            </button>
          )}
        </div>
      )}

      <form onSubmit={saveConfig}>
        <div className="s-section">
          <label className="form-checkbox-row s-field-label" style={{ cursor: 'pointer' }}>
            <input type="checkbox" checked={config.graph_mock} onChange={e => setConfig(c => ({ ...c, graph_mock: e.target.checked }))} />
            <span>Mock mode <small>(no Azure credentials required — good for demo)</small></span>
          </label>
        </div>

        {!config.graph_mock && (
          <div className="form-grid s-section">
            <label className="form-field"><span>Tenant ID</span><input className="input" value={config.tenant_id} onChange={e => setConfig(c => ({ ...c, tenant_id: e.target.value }))} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /></label>
            <label className="form-field"><span>Client ID</span><input className="input" value={config.client_id} onChange={e => setConfig(c => ({ ...c, client_id: e.target.value }))} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /></label>
            <label className="form-field"><span>Client Secret</span><input className="input" type="password" value={config.client_secret} onChange={e => setConfig(c => ({ ...c, client_secret: e.target.value }))} placeholder="Your app secret" /></label>
            <label className="form-field"><span>User email (Graph user)</span><input className="input" type="email" value={config.user_email} onChange={e => setConfig(c => ({ ...c, user_email: e.target.value }))} placeholder="you@company.com" /></label>
          </div>
        )}

        {!config.graph_mock && (
          <div className="s-hint s-section">
            <Info size={13} /> Create an Azure App Registration at <a href="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade" target="_blank" rel="noreferrer" className="link">portal.azure.com</a>. Add <code>Mail.Read</code>, <code>Mail.Send</code>, <code>Calendars.ReadWrite</code> permissions. Use <strong>Public client / native app</strong> redirect URI.
          </div>
        )}

        <div className="editor-actions">
          <button type="submit" className="btn btn-primary" disabled={saving}><Save size={14} />{saving ? 'Saving…' : 'Save Graph settings'}</button>
        </div>
      </form>
    </div>
  );
}

// ══════════════════ PRIVACY TAB ══════════════════════════════════════════════
function PrivacyTab({ showToast }) {
  const [mode, setMode] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchSettings().then(d => setMode(d.pii_mode)).catch(() => { }); }, []);

  const save = async () => {
    setSaving(true);
    try { await saveSettings({ pii_mode: mode }); showToast('PII mode updated.'); }
    catch (e) { showToast(e.message, 'error'); }
    finally { setSaving(false); }
  };

  if (!mode) return <div className="s-loading"><Loader size={20} className="spin" /> Loading…</div>;

  return (
    <div className="stab">
      <div className="stab-header">
        <div><h2>Privacy & PII Protection</h2><p>All email content is masked before reaching the LLM.</p></div>
      </div>

      <div className="s-section">
        <div className="s-field-label">PII Masking Mode</div>
        <div className="pii-mode-list">
          {PII_MODES.map(m => (
            <label key={m.id} className={`pii-mode-card ${mode === m.id ? 'active' : ''}`} onClick={() => setMode(m.id)}>
              <div className="pii-mode-card-header">
                <m.icon size={16} />
                <strong>{m.label}</strong>
                {mode === m.id && <span className="s-badge s-badge--on">Active</span>}
              </div>
              <p>{m.desc}</p>
            </label>
          ))}
        </div>
      </div>

      <div className="s-section s-info-box">
        <Shield size={14} /> Detected PII is replaced with tokens like <code>[[EMAIL_ADDRESS_1]]</code> before the LLM sees the email. After drafting, known-safe values are restored. Any new PII the model invents is stripped.
      </div>

      <div className="editor-actions">
        <button className="btn btn-primary" onClick={save} disabled={saving}><Save size={14} />{saving ? 'Saving…' : 'Save privacy settings'}</button>
      </div>
    </div>
  );
}

// ══════════════════ STORAGE TAB ══════════════════════════════════════════════
function StorageTab({ showToast }) {
  const [dbStatus, setDbStatus] = useState(null);
  const [stats, setStats] = useState(null);
  const [dbUrl, setDbUrl] = useState('postgresql://email_agent:email_agent@localhost:5432/email_agent');
  const [setting, setSetting] = useState(null);
  const [setupLog, setSetupLog] = useState(null);
  const [setuping, setSetuping] = useState(false);

  const load = async () => {
    const [st, sts, cfg] = await Promise.all([
      fetchStorageSetupStatus().catch(() => null),
      fetchStorageStats().catch(() => null),
      fetchSettings().catch(() => null),
    ]);
    setDbStatus(st); setStats(sts); setSetting(cfg);
  };
  useEffect(() => { load(); }, []);

  const runSetup = async () => {
    setSetuping(true); setSetupLog(null);
    try {
      const res = await setupStorage(dbUrl);
      setSetupLog(res.log);
      showToast('Database set up! Restart the server to activate storage.');
      await load();
    } catch (e) { showToast(e.message, 'error'); setSetupLog([e.message]); }
    finally { setSetuping(false); }
  };

  const disableStorage = async () => {
    try { await saveSettings({ storage_enabled: false }); showToast('Storage disabled.'); await load(); }
    catch (e) { showToast(e.message, 'error'); }
  };

  const statusDot = (ok) => ok ? <span className="s-dot s-dot--green" /> : <span className="s-dot s-dot--red" />;

  return (
    <div className="stab">
      <div className="stab-header">
        <div><h2>Storage & Database</h2><p>Encrypted PostgreSQL — persists emails, classifications, calendar events.</p></div>
        <button className="btn btn-secondary" onClick={load}><RefreshCw size={14} /> Refresh</button>
      </div>

      {/* Status panel */}
      <div className="db-status-panel">
        <div className="db-status-row">{statusDot(dbStatus?.docker_running)} Docker daemon</div>
        <div className="db-status-row">{statusDot(dbStatus?.container_exists)} email-agent-postgres container exists</div>
        <div className="db-status-row">{statusDot(dbStatus?.container_running)} Container running</div>
        <div className="db-status-row">{statusDot(dbStatus?.db_reachable)} Database reachable</div>
        <div className="db-status-row">{statusDot(setting?.storage_enabled)} Storage enabled in config</div>
      </div>

      {/* Already working */}
      {dbStatus?.db_reachable && setting?.storage_enabled && stats?.configured && (
        <div className="s-section">
          <div className="s-field-label">Stored records</div>
          <div className="storage-stats">
            {Object.entries(stats.records || {}).map(([type, count]) => (
              <div key={type} className="storage-stat-row">
                <span>{type.replace(/_/g, ' ')}</span><span>{count}</span>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary" style={{ marginTop: 12 }} onClick={disableStorage}><X size={14} /> Disable storage</button>
        </div>
      )}

      {/* Setup wizard */}
      {(!dbStatus?.db_reachable || !setting?.storage_enabled) && (
        <div className="s-section">
          <div className="s-field-label">Set up database</div>

          {!dbStatus?.docker_running && (
            <div className="s-warning">
              <AlertTriangle size={14} /> Docker daemon is not running. Start it first:
              <div className="code-block">sudo dockerd &amp;</div>
              Then come back and click Refresh.
            </div>
          )}

          {dbStatus?.docker_running && (
            <>
              <p className="s-hint" style={{ marginBottom: 12 }}>
                {dbStatus.container_exists
                  ? 'Container exists but is not running. Click "Start Database" to resume.'
                  : 'No container found. Click "One-click Setup" to create and start it automatically.'}
              </p>
              <label className="form-field s-section">
                <span>Database URL</span>
                <input className="input" value={dbUrl} onChange={e => setDbUrl(e.target.value)} />
                <p className="s-hint">Default works if you used the standard setup. Change only if you have a custom PostgreSQL.</p>
              </label>
              <button className="btn btn-primary" onClick={runSetup} disabled={setuping}>
                <Database size={14} /> {setuping ? 'Setting up…' : dbStatus.container_exists ? 'Start Database' : 'One-click Setup'}
              </button>
            </>
          )}

          {/* Manual commands fallback */}
          {!dbStatus?.docker_available && (
            <div className="s-section">
              <p className="s-hint">If Docker is not in PATH or you prefer manual setup:</p>
              <div className="code-block">sudo dockerd &amp;</div>
              <div className="code-block">{`docker run --name email-agent-postgres \\
  -e POSTGRES_USER=email_agent \\
  -e POSTGRES_PASSWORD=email_agent \\
  -e POSTGRES_DB=email_agent \\
  -p 5432:5432 \\
  -v email_agent_pgdata:/var/lib/postgresql/data \\
  -d pgvector/pgvector:pg16`}</div>
              <p className="s-hint">Then restart the server with <code>STORAGE_ENABLED=true</code> in your .env.</p>
            </div>
          )}

          {setupLog && (
            <div className="setup-log">
              {setupLog.map((l, i) => <div key={i}><CheckCircle size={12} /> {l}</div>)}
            </div>
          )}
        </div>
      )}

      {/* OTEL section */}
      {setting && (
        <div className="s-section">
          <div className="s-field-label">OpenTelemetry <small>(optional)</small></div>
          <label className="form-checkbox-row" style={{ marginBottom: 8 }}>
            <input type="checkbox" checked={setting.otel_enabled} onChange={e => setSetting(s => ({ ...s, otel_enabled: e.target.checked }))} />
            <span>Enable tracing</span>
          </label>
          {setting.otel_enabled && (
            <label className="form-field">
              <span>OTLP endpoint</span>
              <input className="input" value={setting.otel_exporter_otlp_endpoint} onChange={e => setSetting(s => ({ ...s, otel_exporter_otlp_endpoint: e.target.value }))} placeholder="http://localhost:4318" />
            </label>
          )}
          <button className="btn btn-secondary" style={{ marginTop: 8 }} onClick={async () => { try { await saveSettings({ otel_enabled: setting.otel_enabled, otel_exporter_otlp_endpoint: setting.otel_exporter_otlp_endpoint }); showToast('Saved.'); } catch (e) { showToast(e.message, 'error'); } }}>
            <Save size={14} /> Save
          </button>
        </div>
      )}
    </div>
  );
}

export default SettingsPage;
