import React, { useState, useEffect, useRef } from 'react';
import {
  X, Send, RotateCcw, Sparkles, ChevronDown,
  Zap, Gauge, Clock, ChevronUp
} from 'lucide-react';
import { composeEmail, fetchAccounts, aiComposeEmail } from '../api';
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

  const [showAI, setShowAI] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiQuality, setAiQuality] = useState('balanced');
  const [showAiQuality, setShowAiQuality] = useState(false);
  const [generatingAI, setGeneratingAI] = useState(false);

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

  const handleAIGenerate = async () => {
    if (!aiPrompt.trim()) return;
    setGeneratingAI(true);
    setError(null);
    try {
      const response = await aiComposeEmail(aiPrompt, aiQuality);
      setBody(response.draft || response.body || '');
      setShowAI(false);
      setAiPrompt('');
    } catch (err) {
      setError(err.message || 'Failed to generate draft.');
    } finally {
      setGeneratingAI(false);
    }
  };

  const hasContent = (to || '').trim() || (subject || '').trim() || (body || '').trim();

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
            <div className="compose-toolbar">
              <button 
                type="button" 
                className={`btn-action compose-ai-toggle ${showAI ? 'active' : ''}`}
                onClick={() => setShowAI(!showAI)}
              >
                <Sparkles size={14} /> AI Assist
              </button>
            </div>

            {showAI && (
              <div className="compose-ai-panel animate-slide-down">
                <input
                  className="input compose-ai-input"
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  placeholder="What should this email be about?"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAIGenerate();
                    }
                  }}
                />
                <div className="compose-ai-actions">
                  <div className="quality-selector-wrapper">
                    <button
                      type="button"
                      className="btn btn-action"
                      onClick={() => setShowAiQuality(!showAiQuality)}
                      disabled={generatingAI}
                    >
                      {(() => {
                        const SelectedIcon = QUALITY_OPTIONS.find(q => q.value === aiQuality)?.icon || Zap;
                        return <SelectedIcon size={14} />;
                      })()}
                      {QUALITY_OPTIONS.find(q => q.value === aiQuality)?.label}
                      {showAiQuality ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>
                    {showAiQuality && (
                      <div className="quality-dropdown">
                        {QUALITY_OPTIONS.map(({ value, label, icon: Icon, desc }) => (
                          <button
                            key={value}
                            type="button"
                            className={`quality-option ${aiQuality === value ? 'active' : ''}`}
                            onClick={() => { setAiQuality(value); setShowAiQuality(false); }}
                          >
                            <Icon size={14} />
                            <div>
                              <div className="quality-option-label">{label}</div>
                              <div className="quality-option-desc">{desc}</div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleAIGenerate}
                    disabled={generatingAI || !aiPrompt.trim()}
                  >
                    {generatingAI ? (
                      <><RotateCcw size={14} className="spin" /> Generating...</>
                    ) : (
                      <><Sparkles size={14} /> Generate</>
                    )}
                  </button>
                </div>
              </div>
            )}

            <textarea
              className="compose-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder={showAI ? '' : 'Write your message...'}
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
