import { useState, useEffect, useRef, useMemo } from 'react';
import {
  Shield, Sparkles, RotateCcw, Send, Zap, Clock, Gauge,
  ChevronDown, ChevronUp, Reply, ReplyAll, Forward, MessageSquare, Check
} from 'lucide-react';
import {
  classifyEmail, draftReply, approveDraft, fetchEmail,
  markAsRead, fetchThread, sendReply
} from '../api';
import { formatFullDate, formatDate, senderColor, formatSender } from '../utils';
import './EmailDetail.css';

const QUALITY_OPTIONS = [
    { value: 'quick', label: 'Quick', icon: Zap, desc: 'Fast, concise response' },
    { value: 'balanced', label: 'Balanced', icon: Gauge, desc: 'Optimal quality' },
    { value: 'thorough', label: 'Thorough', icon: Clock, desc: 'Detailed, comprehensive' },
];

function formatPlainText(text) {
    if (!text) return null;
    try {
        const lines = text.split('\n');
        return lines.map((line, i) => {
            const isQuote = line.trim().startsWith('>');
            const elements = line.split(/(https?:\/\/[^\s]+)/).map((part, j) => {
                if (part && (part.startsWith('http://') || part.startsWith('https://'))) {
                    return <a key={j} href={part} target="_blank" rel="noopener noreferrer" style={{color: 'var(--accent)'}}>{part}</a>;
                }
                return part;
            });

            if (isQuote) {
                return <blockquote key={i} className="email-quote">{elements}</blockquote>;
            }
            return <span key={i}>{elements}<br /></span>;
        });
    } catch (err) {
        return <div style={{ color: 'red' }}>Format Text Error: {err.message}</div>;
    }
}

function BodyRenderer({ msg, whiteMode }) {
    const [iframeHeight, setIframeHeight] = useState('0px');
    const [showImages, setShowImages] = useState(false);

    const { safeHtml, hasBlockedImages, renderError } = useMemo(() => {
        try {
            if (!msg.html_body) return { safeHtml: null, hasBlockedImages: false, renderError: null };
            if (showImages) return { safeHtml: msg.html_body, hasBlockedImages: false, renderError: null };

            const lowerBody = msg.html_body.toLowerCase();
            const hasImg = lowerBody.includes('<img') && lowerBody.includes('http');
            const hasUrl = lowerBody.includes('url(') && lowerBody.includes('http');
            
            if (!hasImg && !hasUrl) {
                return { safeHtml: msg.html_body, hasBlockedImages: false, renderError: null };
            }

            let modifiedHtml = msg.html_body;
            let blocked = false;

            if (hasUrl) {
                const cleaned = modifiedHtml.replace(/url\((['"]?)(https?:\/\/[^'")\s]+)\1\)/gi, 'url()');
                if (cleaned !== modifiedHtml) {
                    modifiedHtml = cleaned;
                    blocked = true;
                }
            }

            const parser = new DOMParser();
            const doc = parser.parseFromString(modifiedHtml, 'text/html');
            
            const imgs = Array.from(doc.querySelectorAll('img'));
            const remoteImgs = imgs.filter(img => (img.src || '').toLowerCase().startsWith('http'));

            if (remoteImgs.length > 0) {
                remoteImgs.forEach(img => {
                    img.removeAttribute('srcset');
                    img.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxIiBoZWlnaHQ9IjEiPjwvc3ZnPg==';
                    img.style.border = '1px dashed #ccc';
                    img.title = 'Remote image blocked. Click "Load Images" to display.';
                });
                blocked = true;
            }

            if (blocked) {
                return { safeHtml: doc.documentElement.outerHTML, hasBlockedImages: true, renderError: null };
            }
            
            return { safeHtml: msg.html_body, hasBlockedImages: false, renderError: null };
        } catch (err) {
            return { safeHtml: null, hasBlockedImages: false, renderError: err.message };
        }
    }, [msg.html_body, showImages]);

    if (renderError) {
        return <div style={{ color: 'red', padding: '20px' }}>BodyRenderer Error: {renderError}</div>;
    }

    if (msg.html_body) {
        return (
            <div className="email-body-wrapper" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {hasBlockedImages && !showImages && (
                    <div className="blocked-images-banner" style={{ padding: '8px 12px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '12px', color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Shield size={14} /> Remote images blocked to protect your privacy.
                        </span>
                        <button className="btn btn-secondary" style={{ fontSize: '11px', padding: '4px 8px' }} onClick={() => setShowImages(true)}>
                            Load Images
                        </button>
                    </div>
                )}
                {/* 
                  SECURITY NOTE FOR IFRAME SANDBOX:
                  allow-same-origin is REQUIRED here solely to access e.target.contentWindow.document
                  in order to inject CSS and measure height for auto-resizing.
                  DO NOT ADD allow-scripts to this sandbox. allow-scripts + allow-same-origin 
                  will completely defeat the sandbox and allow the email to access parent DOM/cookies!
                  allow-popups-to-escape-sandbox is intentionally included so <a target="_blank"> 
                  opens in a normal, fully functional browser tab.
                */}
                <iframe
                    key={whiteMode ? 'white' : 'dark'}
                    title={`Email Body ${msg.id}`}
                    srcDoc={safeHtml}
                    sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin"
                    className="email-iframe"
                    style={{ width: '100%', height: iframeHeight, border: 'none', overflow: 'hidden', backgroundColor: whiteMode ? '#fff' : 'transparent', borderRadius: whiteMode ? '8px' : '0' }}
                    onLoad={(e) => {
                        const doc = e.target.contentWindow?.document;
                        if (!doc) return;
                        
                        const style = doc.createElement('style');
                        if (whiteMode) {
                            style.textContent = `
                                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; padding: 16px; margin: 0; word-wrap: break-word; color: #000; background: #fff; }
                                a { color: #0000EE; }
                            `;
                        } else {
                            style.textContent = `
                                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; padding: 0; margin: 0; word-wrap: break-word; color: #333; }
                                @media (prefers-color-scheme: dark) {
                                   body { color: #e5e7eb; }
                                   a { color: #60a5fa; }
                                }
                            `;
                        }
                        doc.head.appendChild(style);
                        
                        const resize = () => {
                            setIframeHeight((doc.documentElement.scrollHeight + 20) + 'px');
                        };
                        resize();
                        setTimeout(resize, 100);
                        
                        try {
                            new MutationObserver(resize).observe(doc.body, { childList: true, subtree: true, attributes: true });
                            // Wait for image loads to properly resize
                            const imgs = doc.querySelectorAll('img');
                            imgs.forEach(img => {
                                img.addEventListener('load', resize);
                            });
                        } catch (err) {}
                    }}
                />
            </div>
        );
    }

    return (
        <div className="email-body-text" style={whiteMode ? { backgroundColor: '#fff', color: '#000', padding: '16px', borderRadius: '8px' } : {}}>
            {formatPlainText(msg.body)}
        </div>
    );
}

function ThreadMessage({ msg, isExpanded, onToggle, isLatest, whiteMode }) {
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
                    <BodyRenderer msg={msg} whiteMode={whiteMode} />
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
    const [whiteMode, setWhiteMode] = useState(false);

    // Thread state
    const [thread, setThread] = useState([]);
    const [expandedMsgs, setExpandedMsgs] = useState(new Set());
    const [loadingThread, setLoadingThread] = useState(false);

    // Inline reply state
    const [showReply, setShowReply] = useState(false);
    const [replyAction, setReplyAction] = useState('reply');
    const [replyTo, setReplyTo] = useState('');
    const [replyCc, setReplyCc] = useState('');
    const [replyBcc, setReplyBcc] = useState('');
    const [replyBody, setReplyBody] = useState('');
    const [sendingReply, setSendingReply] = useState(false);

    const replyRef = useRef(null);

    const openReply = (action) => {
        setReplyAction(action);
        
        let initialTo = '';
        let initialCc = '';
        let initialBody = '';
        
        if (action === 'reply') {
            initialTo = email.sender;
        } else if (action === 'reply_all') {
            const allTo = [email.sender, ...(email.recipients || [])];
            initialTo = [...new Set(allTo)].join(', ');
            initialCc = (email.cc || []).join(', ');
        } else if (action === 'forward') {
            initialBody = `\n\n---------- Forwarded message ---------\nFrom: ${email.sender}\nDate: ${formatFullDate(email.timestamp)}\nSubject: ${email.subject}\nTo: ${(email.recipients || []).join(', ')}\n\n${email.body}`;
        }
        
        setReplyTo(initialTo);
        setReplyCc(initialCc);
        setReplyBcc('');
        setReplyBody(initialBody);
        
        setShowReply(true);
        setTimeout(() => replyRef.current?.focus(), 100);
    };

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

    // Auto mark-as-read (must be before early return to satisfy Rules of Hooks)
    useEffect(() => {
        if (email && !email.is_read) {
            markAsRead(email.id).catch(() => {});
        }
    }, [email?.id, email?.is_read]);

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
                setReplyAction('reply');
                setReplyTo(email.sender);
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
            // Sort thread by timestamp to guarantee we get the absolute newest message
            const sortedThread = [...thread].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            const latestReceived = sortedThread.reverse().find(m => !m.is_sent);
            const replyTargetId = latestReceived?.id || email.id;

            const result = await approveDraft(replyTargetId);
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
            showToast('Reply sent successfully! ✉️');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    const handleSendReply = async () => {
        if (!replyBody.trim() || busy) return;
        setBusy('reply');
        try {
            // Sort thread by timestamp to guarantee we get the absolute newest message
            const sortedThread = [...thread].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            const latestReceived = sortedThread.reverse().find(m => !m.is_sent);
            const replyTargetId = latestReceived?.id || email.id;

            const toList = replyTo.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean);
            const ccList = replyCc.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean);
            const bccList = replyBcc.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean);

            await sendReply(replyTargetId, replyBody, toList, ccList, bccList, replyAction);
            setReplyBody('');
            setShowReply(false);
            // Refresh thread
            const msgs = await fetchThread(email.id);
            setThread(msgs);
            if (msgs.length > 0) {
                setExpandedMsgs(new Set([msgs[msgs.length - 1].id]));
            }
            onReload?.();
            showToast('Reply sent successfully! ✉️');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };

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
                <button className={`btn btn-action ${whiteMode ? 'active' : ''}`} onClick={() => setWhiteMode(!whiteMode)}>
                    View in {whiteMode ? 'Dark' : 'White'} Mode
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
                <div className="btn-group" style={{ display: 'flex', gap: '4px' }}>
                    <button
                        className="btn btn-action reply-toggle-btn"
                        onClick={() => openReply('reply')}
                        title="Reply"
                    >
                        <Reply size={14} /> Reply
                    </button>
                    <button
                        className="btn btn-action reply-toggle-btn"
                        onClick={() => openReply('reply_all')}
                        title="Reply All"
                    >
                        <ReplyAll size={14} /> Reply All
                    </button>
                    <button
                        className="btn btn-action reply-toggle-btn"
                        onClick={() => openReply('forward')}
                        title="Forward"
                    >
                        <Forward size={14} /> Forward
                    </button>
                </div>
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
                                whiteMode={whiteMode}
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
                        <BodyRenderer msg={email} whiteMode={whiteMode} />
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
                            {replyAction === 'forward' ? <Forward size={14} /> : <Reply size={14} />}
                            <span style={{ textTransform: 'capitalize' }}>{replyAction.replace('_', ' ')}</span>
                        </div>
                        <div className="inline-reply-fields" style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '0 12px 12px 12px', borderBottom: '1px solid var(--border)' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ width: '30px', color: 'var(--text-light)', fontSize: '13px' }}>To:</span>
                                <input className="input compose-input" value={replyTo} onChange={e => setReplyTo(e.target.value)} style={{ flex: 1, padding: '4px 8px', fontSize: '13px' }} placeholder="recipients" />
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ width: '30px', color: 'var(--text-light)', fontSize: '13px' }}>Cc:</span>
                                <input className="input compose-input" value={replyCc} onChange={e => setReplyCc(e.target.value)} style={{ flex: 1, padding: '4px 8px', fontSize: '13px' }} placeholder="cc" />
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ width: '30px', color: 'var(--text-light)', fontSize: '13px' }}>Bcc:</span>
                                <input className="input compose-input" value={replyBcc} onChange={e => setReplyBcc(e.target.value)} style={{ flex: 1, padding: '4px 8px', fontSize: '13px' }} placeholder="bcc" />
                            </div>
                        </div>
                        <textarea
                            ref={replyRef}
                            className="inline-reply-body"
                            value={replyBody}
                            onChange={(e) => setReplyBody(e.target.value)}
                            placeholder="Type your message..."
                            rows={8}
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
                                disabled={!!busy || !replyBody.trim()}
                            >
                                {busy === 'reply' ? (
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
