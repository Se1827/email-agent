import { useState, useEffect, useRef } from 'react';
import {
  Shield, Sparkles, RotateCcw, Send, Zap, Clock, Gauge,
  ChevronDown, ChevronUp, Reply, MessageSquare, Check
} from 'lucide-react';
import {
  classifyEmail, draftReply, approveDraft, fetchEmail,
  markAsRead, fetchThread, sendReply
} from '../api';
import { formatFullDate, formatDate, senderColor, formatSender } from '../utils';
import { ScenarioStrip } from './SmartCard';
import './EmailDetail.css';

const QUALITY_OPTIONS = [
    { value: 'quick', label: 'Quick', icon: Zap, desc: 'Fast, concise response' },
    { value: 'balanced', label: 'Balanced', icon: Gauge, desc: 'Optimal quality' },
    { value: 'thorough', label: 'Thorough', icon: Clock, desc: 'Detailed, comprehensive' },
];

function ThreadMessage({ msg, isExpanded, onToggle, isLatest }) {
    const isSent = msg.is_sent;

    return (
        <div className={`thread-msg ${isExpanded ? 'thread-msg-expanded' : 'thread-msg-collapsed'} ${isSent ? 'thread-msg-sent' : ''}`}>
            <div className="thread-msg-header" onClick={onToggle}>
                <div className="thread-msg-sender-row">
                    <div className="thread-msg-avatar" style={{ background: senderColor(msg.sender) }}>
                        {formatSender(msg.sender).charAt(0).toUpperCase()}
                    </div>
                    <div className="thread-msg-sender-info">
                        <span className="thread-msg-sender-name">
                            {formatSender(msg.sender)}
                            {isSent && <span className="sent-badge">Sent</span>}
                        </span>
                        {!isExpanded && (
                            <span className="thread-msg-snippet">
                                {msg.body.slice(0, 100).replace(/\n/g, ' ')}
                            </span>
                        )}
                    </div>
                </div>
                <div className="thread-msg-meta">
                    <span className="thread-msg-date">{formatDate(msg.timestamp)}</span>
                    {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </div>
            </div>
            {isExpanded && (
                <div className="thread-msg-body animate-fade-in">
                    <div className="thread-msg-details">
                        <span className="thread-msg-detail">From: {msg.sender}</span>
                        <span className="thread-msg-detail">To: {msg.recipients?.join(', ')}</span>
                        {msg.cc?.length > 0 && (
                            <span className="thread-msg-detail">Cc: {msg.cc.join(', ')}</span>
                        )}
                        <span className="thread-msg-detail">{formatFullDate(msg.timestamp)}</span>
                    </div>
                    <pre className="email-body-text">{msg.body}</pre>
                </div>
            )}
        </div>
    );
}

function EmailDetail({ email, onUpdate, onReload }) {
    const [busy, setBusy] = useState(null);
    const [toast, setToast] = useState(null);
    const [draftQuality, setDraftQuality] = useState('balanced');
    const [editedDraft, setEditedDraft] = useState(null);
    const [showQuality, setShowQuality] = useState(false);

    // Thread state
    const [thread, setThread] = useState([]);
    const [expandedMsgs, setExpandedMsgs] = useState(new Set());
    const [loadingThread, setLoadingThread] = useState(false);

    // Inline reply state
    const [showReply, setShowReply] = useState(false);
    const [replyBody, setReplyBody] = useState('');
    const [sendingReply, setSendingReply] = useState(false);

    const replyRef = useRef(null);

    // Load thread when email changes
    useEffect(() => {
        if (!email) return;
        setLoadingThread(true);
        fetchThread(email.id)
            .then(msgs => {
                setThread(msgs);
                // Expand the latest message by default
                if (msgs.length > 0) {
                    setExpandedMsgs(new Set([msgs[msgs.length - 1].id]));
                }
            })
            .catch(() => setThread([email]))
            .finally(() => setLoadingThread(false));
        setShowReply(false);
        setReplyBody('');
    }, [email?.id]);

    if (!email) {
        return (
            <div className="email-detail email-detail-empty" id="email-detail-empty">
                <div className="empty-state">
                    <Sparkles size={40} className="empty-state-icon" />
                    <p className="empty-state-title">Select an email</p>
                    <p className="empty-state-desc">Choose an email from the list to view the conversation, classify it with AI, and send real replies.</p>
                </div>
            </div>
        );
    }

    const showToast = (msg, type = 'success') => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 3500);
    };

    const toggleMsg = (msgId) => {
        setExpandedMsgs(prev => {
            const next = new Set(prev);
            if (next.has(msgId)) next.delete(msgId);
            else next.add(msgId);
            return next;
        });
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
            // Pre-fill the reply area with the draft
            if (updated.draft_reply) {
                setReplyBody(updated.draft_reply.body);
                setShowReply(true);
                setTimeout(() => replyRef.current?.focus(), 100);
            }
            showToast('AI draft generated');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    const handleApprove = async () => {
        setBusy('approve');
        try {
            const result = await approveDraft(email.id);
            const updated = await fetchEmail(email.id);
            onUpdate(updated);
            setEditedDraft(null);
            setReplyBody('');
            setShowReply(false);
            // Refresh thread to show the sent reply
            fetchThread(email.id).then(msgs => {
                setThread(msgs);
                if (msgs.length > 0) {
                    setExpandedMsgs(new Set([msgs[msgs.length - 1].id]));
                }
            });
            showToast('Reply sent successfully!');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    const handleSendReply = async () => {
        if (!replyBody.trim()) return;
        setSendingReply(true);
        try {
            await sendReply(email.id, replyBody);
            setReplyBody('');
            setShowReply(false);
            // Refresh thread
            const msgs = await fetchThread(email.id);
            setThread(msgs);
            if (msgs.length > 0) {
                setExpandedMsgs(new Set([msgs[msgs.length - 1].id]));
            }
            onReload?.();
            showToast('Reply sent successfully!');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setSendingReply(false);
        }
    };

    // Auto mark-as-read
    if (!email.is_read) {
        markAsRead(email.id).catch(() => {});
    }

    const cls = email.classification;
    const draft = email.draft_reply;
    const threadCount = thread.length;
    const hasThread = threadCount > 1;

    // Collect unique participants
    const participants = [...new Set(thread.flatMap(m => [m.sender, ...(m.recipients || [])]))];

    return (
        <div className="email-detail animate-fade-in" id="email-detail">
            {toast && (
                <div className={`toast toast-${toast.type}`}>{toast.msg}</div>
            )}

            {/* Thread Header */}
            <div className="detail-header">
                <h2 className="detail-subject">{email.subject}</h2>
                <ScenarioStrip email={email} />
                <div className="thread-info-row">
                    {hasThread && (
                        <div className="thread-count-badge">
                            <MessageSquare size={12} />
                            {threadCount} messages
                        </div>
                    )}
                    <div className="thread-participants">
                        {participants.slice(0, 4).map((p, i) => (
                            <div
                                key={p}
                                className="thread-participant-avatar"
                                style={{ background: senderColor(p), zIndex: 4 - i }}
                                title={p}
                            >
                                {formatSender(p).charAt(0).toUpperCase()}
                            </div>
                        ))}
                        {participants.length > 4 && (
                            <span className="thread-more-count">+{participants.length - 4}</span>
                        )}
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
                                <><Zap size={14} /> {draft ? 'Re-draft' : 'AI Draft'}</>
                            )}
                        </button>
                    </>
                )}
                {draft && (
                    <button className="btn btn-approve" onClick={handleApprove} disabled={!!busy} id="btn-approve">
                        {busy === 'approve' ? (
                            <><RotateCcw size={14} className="spin" /> Sending...</>
                        ) : (
                            <><Send size={14} /> Approve &amp; Send</>
                        )}
                    </button>
                )}
                <div className="detail-actions-spacer" />
                <button
                    className="btn btn-action reply-toggle-btn"
                    onClick={() => { setShowReply(!showReply); setTimeout(() => replyRef.current?.focus(), 100); }}
                >
                    <Reply size={14} /> Reply
                </button>
            </div>

            {/* Thread / Conversation */}
            <div className="thread-container">
                {loadingThread ? (
                    <div className="thread-loading">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="email-row-skeleton shimmer-bg" style={{ height: 60, marginBottom: 8, borderRadius: 10 }} />
                        ))}
                    </div>
                ) : hasThread ? (
                    <div className="thread-messages">
                        {thread.map((msg, idx) => (
                            <ThreadMessage
                                key={msg.id}
                                msg={msg}
                                isExpanded={expandedMsgs.has(msg.id)}
                                onToggle={() => toggleMsg(msg.id)}
                                isLatest={idx === thread.length - 1}
                            />
                        ))}
                    </div>
                ) : (
                    /* Single email — show full body */
                    <div className="detail-body">
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
                                {email.cc?.length > 0 && <span className="detail-recipients">Cc: {email.cc.join(', ')}</span>}
                                <span className="detail-date">{formatFullDate(email.timestamp)}</span>
                            </div>
                        </div>
                        <pre className="email-body-text">{email.body}</pre>
                    </div>
                )}

                {/* AI Draft (shown if draft exists but reply not open) */}
                {draft && !showReply && (
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
                            value={editedDraft !== null ? editedDraft : draft.body}
                            onChange={(e) => setEditedDraft(e.target.value)}
                            rows={6}
                        />
                        <div className="draft-footer">
                            <span className="draft-hint">Edit the draft above, then approve to send via SMTP</span>
                            <div className="draft-pii-shield">
                                <Shield size={12} />
                                PII Shield Active
                            </div>
                        </div>
                    </div>
                )}

                {/* Inline Reply Composer */}
                {showReply && (
                    <div className="inline-reply animate-slide-up">
                        <div className="inline-reply-header">
                            <Reply size={14} />
                            <span>Reply to {formatSender(email.sender)}</span>
                        </div>
                        <textarea
                            ref={replyRef}
                            className="inline-reply-body"
                            value={replyBody}
                            onChange={(e) => setReplyBody(e.target.value)}
                            placeholder="Type your reply..."
                            rows={5}
                        />
                        <div className="inline-reply-actions">
                            {cls && (
                                <button
                                    className="btn btn-action"
                                    onClick={handleDraft}
                                    disabled={!!busy}
                                    title="Generate AI draft and fill reply"
                                >
                                    {busy === 'draft' ? (
                                        <><RotateCcw size={13} className="spin" /> Generating...</>
                                    ) : (
                                        <><Sparkles size={13} /> AI Draft</>
                                    )}
                                </button>
                            )}
                            <div className="inline-reply-spacer" />
                            <button
                                className="btn btn-secondary"
                                onClick={() => { setShowReply(false); setReplyBody(''); }}
                            >
                                Cancel
                            </button>
                            <button
                                className="btn btn-primary"
                                onClick={handleSendReply}
                                disabled={sendingReply || !replyBody.trim()}
                            >
                                {sendingReply ? (
                                    <><RotateCcw size={14} className="spin" /> Sending...</>
                                ) : (
                                    <><Send size={14} /> Send Reply</>
                                )}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default EmailDetail;
