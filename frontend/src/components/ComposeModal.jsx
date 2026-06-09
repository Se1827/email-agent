import { useState, useEffect, useRef } from 'react';
import {
  X, Send, RotateCcw, Sparkles, ChevronDown,
  Zap, Gauge, Clock, ChevronUp
} from 'lucide-react';
import { composeEmail, fetchAccounts, draftReply } from '../api';
import './ComposeModal.css';

const QUALITY_OPTIONS = [
  { value: 'quick', label: 'Quick', icon: Zap, desc: 'Fast, concise' },
  { value: 'balanced', label: 'Balanced', icon: Gauge, desc: 'Optimal quality' },
  { value: 'thorough', label: 'Thorough', icon: Clock, desc: 'Detailed' },
];

function ComposeModal({ open, onClose, onSent, accounts: propAccounts }) {
  const [to, setTo] = useState('');
  const [cc, setCc] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [accountId, setAccountId] = useState('');
  const [accounts, setAccounts] = useState(propAccounts || []);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [showCc, setShowCc] = useState(false);
  const modalRef = useRef(null);

  useEffect(() => {
    if (propAccounts && propAccounts.length > 0) {
      setAccounts(propAccounts);
      if (!accountId) setAccountId(propAccounts[0].id);
    } else if (open && accounts.length === 0) {
      fetchAccounts().then(accs => {
        setAccounts(accs);
        if (!accountId && accs.length > 0) setAccountId(accs[0].id);
      }).catch(() => {});
    }
  }, [open, propAccounts]);

  useEffect(() => {
    if (open) {
      const handler = (e) => { if (e.key === 'Escape') onClose(); };
      window.addEventListener('keydown', handler);
      return () => window.removeEventListener('keydown', handler);
    }
  }, [open, onClose]);

  if (!open) return null;

  const currentAccount = accounts.find(a => a.id === accountId);

  const parseAddresses = (str) =>
    str.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean);

  const handleSend = async (e) => {
    e.preventDefault();
    const toList = parseAddresses(to);
    if (toList.length === 0) {
      setError('At least one recipient is required.');
      return;
    }
    if (!subject.trim()) {
      setError('Subject is required.');
      return;
    }
    if (!body.trim()) {
      setError('Message body is required.');
      return;
    }

    setSending(true);
    setError(null);
    try {
      const ccList = showCc ? parseAddresses(cc) : [];
      await composeEmail(toList, ccList, subject, body, accountId);
      onSent?.();
      // Reset
      setTo(''); setCc(''); setSubject(''); setBody('');
      setShowCc(false); setError(null);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to send email.');
    } finally {
      setSending(false);
    }
  };

  const hasContent = to.trim() || subject.trim() || body.trim();

  const handleClose = () => {
    if (hasContent) {
      if (window.confirm('Discard this email?')) {
        setTo(''); setCc(''); setSubject(''); setBody('');
        setShowCc(false); setError(null);
        onClose();
      }
    } else {
      onClose();
    }
  };

  return (
    <div className="compose-overlay" onClick={handleClose}>
      <div className="compose-modal animate-slide-up" onClick={e => e.stopPropagation()} ref={modalRef}>
        <div className="compose-header">
          <h3 className="compose-title">New Message</h3>
          <button className="btn-icon compose-close" onClick={handleClose} title="Close">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSend} className="compose-form">
          {/* Account selector */}
          {accounts.length > 1 && (
            <div className="compose-field compose-from-field">
              <label className="compose-label">From</label>
              <select
                className="select compose-select"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
              >
                {accounts.filter(a => a.is_active).map(acc => (
                  <option key={acc.id} value={acc.id}>
                    {acc.name} &lt;{acc.email}&gt;
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="compose-field">
            <label className="compose-label">To</label>
            <input
              className="input compose-input"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="recipient@example.com"
              autoFocus
            />
            {!showCc && (
              <button type="button" className="compose-cc-toggle" onClick={() => setShowCc(true)}>
                Cc
              </button>
            )}
          </div>

          {showCc && (
            <div className="compose-field">
              <label className="compose-label">Cc</label>
              <input
                className="input compose-input"
                value={cc}
                onChange={(e) => setCc(e.target.value)}
                placeholder="cc@example.com"
              />
            </div>
          )}

          <div className="compose-field">
            <label className="compose-label">Subject</label>
            <input
              className="input compose-input"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Email subject"
            />
          </div>

          <div className="compose-body-wrapper">
            <textarea
              className="compose-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write your message..."
              rows={12}
            />
          </div>

          {error && <div className="compose-error">{error}</div>}

          <div className="compose-footer">
            <div className="compose-footer-left">
              {currentAccount && (
                <span className="compose-from-hint">
                  Sending as <strong>{currentAccount.email}</strong>
                </span>
              )}
            </div>
            <div className="compose-footer-right">
              <button type="button" className="btn btn-secondary" onClick={handleClose} disabled={sending}>
                Discard
              </button>
              <button className="btn btn-primary compose-send-btn" disabled={sending}>
                {sending ? (
                  <><RotateCcw size={14} className="spin" /> Sending...</>
                ) : (
                  <><Send size={14} /> Send</>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ComposeModal;
