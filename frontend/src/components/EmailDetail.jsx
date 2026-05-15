import { useState } from 'react';
import {
  Shield, Sparkles, RotateCcw, Send, Zap, Clock, Gauge,
  ChevronDown, ChevronUp
} from 'lucide-react';
import { classifyEmail, draftReply, approveDraft, fetchEmail, markAsRead } from '../api';
import { formatFullDate, senderColor, formatSender } from '../utils';
import './EmailDetail.css';

const QUALITY_OPTIONS = [
    { value: 'quick', label: 'Quick', icon: Zap, desc: 'Fast, concise response' },
    { value: 'balanced', label: 'Balanced', icon: Gauge, desc: 'Optimal quality' },
    { value: 'thorough', label: 'Thorough', icon: Clock, desc: 'Detailed, comprehensive' },
];

function EmailDetail({ email, onUpdate, onReload }) {
    const [busy, setBusy] = useState(null);
    const [toast, setToast] = useState(null);
    const [draftQuality, setDraftQuality] = useState('balanced');
    const [editedDraft, setEditedDraft] = useState(null);
    const [showQuality, setShowQuality] = useState(false);

    if (!email) {
        return (
            <div className="email-detail email-detail-empty" id="email-detail-empty">
                <div className="empty-state">
                    <Sparkles size={40} className="empty-state-icon" />
                    <p className="empty-state-title">Select an email</p>
                    <p className="empty-state-desc">Choose an email from the list to view its contents, classify it with AI, and generate smart replies.</p>
                </div>
            </div>
        );
    }

    const showToast = (msg, type = 'success') => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 3000);
    };

    const handleClassify = async () => {
        setBusy('classify');
        try {
            await classifyEmail(email.id);
            const updated = await fetchEmail(email.id);
            onUpdate(updated);
            showToast('Classified successfully');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    const handleDraft = async () => {
        setBusy('draft');
        try {
            await draftReply(email.id, draftQuality);
            const updated = await fetchEmail(email.id);
            onUpdate(updated);
            setEditedDraft(null);
            showToast('Draft generated');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    const handleApprove = async () => {
        setBusy('approve');
        try {
            await approveDraft(email.id);
            const updated = await fetchEmail(email.id);
            onUpdate(updated);
            setEditedDraft(null);
            showToast('Reply sent (simulated)');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    // Auto mark-as-read
    if (!email.is_read) {
        markAsRead(email.id).catch(() => {});
    }

    const cls = email.classification;
    const draft = email.draft_reply;
    const draftBody = editedDraft !== null ? editedDraft : (draft?.body || '');

    return (
        <div className="email-detail animate-fade-in" id="email-detail">
            {toast && (
                <div className={`toast toast-${toast.type}`}>{toast.msg}</div>
            )}

            {/* Header */}
            <div className="detail-header">
                <h2 className="detail-subject">{email.subject}</h2>
                <div className="detail-meta">
                    <div className="detail-sender-row">
                        <div className="detail-avatar" style={{ background: senderColor(email.sender) }}>
                            {formatSender(email.sender).charAt(0).toUpperCase()}
                        </div>
                        <div>
                            <span className="detail-sender-name">{formatSender(email.sender)}</span>
                            <span className="detail-sender-email">{email.sender}</span>
                        </div>
                    </div>
                    <div className="detail-meta-right">
                        <span className="detail-recipients">To: {email.recipients.join(', ')}</span>
                        <span className="detail-date">{formatFullDate(email.timestamp)}</span>
                    </div>
                </div>

                {cls && (
                    <div className="detail-classification">
                        <span className={`priority-badge priority-${cls.priority}`}>
                            {cls.priority}
                        </span>
                        <span className={`category-badge category-b-${cls.category}`}>
                            {cls.category}
                        </span>
                        <span className="confidence-ring">
                            <svg width="24" height="24" viewBox="0 0 24 24">
                                <circle cx="12" cy="12" r="10" fill="none" stroke="var(--border)" strokeWidth="2" />
                                <circle cx="12" cy="12" r="10" fill="none" stroke="var(--accent)"
                                    strokeWidth="2"
                                    strokeDasharray={`${cls.confidence * 62.83} 62.83`}
                                    strokeLinecap="round"
                                    transform="rotate(-90 12 12)"
                                />
                            </svg>
                            <span className="confidence-text">{(cls.confidence * 100).toFixed(0)}%</span>
                        </span>
                        {cls.reasoning && (
                            <span className="reasoning"><Sparkles size={12} /> {cls.reasoning}</span>
                        )}
                    </div>
                )}
            </div>

            {/* Actions */}
            <div className="detail-actions">
                <button className="btn btn-action" onClick={handleClassify} disabled={!!busy} id="btn-classify">
                    {busy === 'classify' ? (
                        <><RotateCcw size={14} className="spin" /> Classifying...</>
                    ) : (
                        <><Sparkles size={14} /> {cls ? 'Re-classify' : 'Classify'}</>
                    )}
                </button>
                {cls && (
                    <>
                        <div className="quality-selector-wrapper">
                            <button
                                className="btn btn-action"
                                onClick={() => setShowQuality(!showQuality)}
                                disabled={!!busy}
                            >
                                <Gauge size={14} />
                                {QUALITY_OPTIONS.find(q => q.value === draftQuality)?.label}
                                {showQuality ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            </button>
                            {showQuality && (
                                <div className="quality-dropdown">
                                    {QUALITY_OPTIONS.map(({ value, label, icon: Icon, desc }) => (
                                        <button
                                            key={value}
                                            className={`quality-option ${draftQuality === value ? 'active' : ''}`}
                                            onClick={() => { setDraftQuality(value); setShowQuality(false); }}
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
                        <button className="btn btn-action" onClick={handleDraft} disabled={!!busy} id="btn-draft">
                            {busy === 'draft' ? (
                                <><RotateCcw size={14} className="spin" /> Drafting...</>
                            ) : (
                                <><Zap size={14} /> {draft ? 'Re-draft' : 'Draft Reply'}</>
                            )}
                        </button>
                    </>
                )}
                {draft && (
                    <button className="btn btn-approve" onClick={handleApprove} disabled={!!busy} id="btn-approve">
                        {busy === 'approve' ? (
                            <><RotateCcw size={14} className="spin" /> Sending...</>
                        ) : (
                            <><Send size={14} /> Approve & Send</>
                        )}
                    </button>
                )}
            </div>

            {/* Body */}
            <div className="detail-body">
                <pre className="email-body-text">{email.body}</pre>
            </div>

            {/* Draft */}
            {draft && (
                <div className="detail-draft animate-slide-up">
                    <div className="draft-header">
                        <h3 className="draft-title">
                            <Sparkles size={14} /> AI Draft Reply
                            <span className="draft-quality-badge">{draft.quality || draftQuality}</span>
                        </h3>
                    </div>
                    {draft.pii_redacted && (
                        <div className="draft-pii-warning">
                            <Shield size={13} />
                            PII protected: {draft.redacted_types.join(', ')}
                        </div>
                    )}
                    <textarea
                        className="draft-editor"
                        value={draftBody}
                        onChange={(e) => setEditedDraft(e.target.value)}
                        rows={6}
                    />
                    <div className="draft-footer">
                        <span className="draft-hint">Edit the draft above before approving</span>
                        <div className="draft-pii-shield">
                            <Shield size={12} />
                            PII Shield Active
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default EmailDetail;
