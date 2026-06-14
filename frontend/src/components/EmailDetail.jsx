import { useState, useEffect, useRef, useMemo } from 'react';
import {
  Shield, Sparkles, RotateCcw, Send, Zap, Clock, Gauge,
  ChevronDown, ChevronUp, Reply, ReplyAll, Forward, MessageSquare, Check,
  Paperclip, Download, ListChecks, CheckCircle, XCircle, Info,
  Calendar, CalendarPlus, CalendarX
} from 'lucide-react';
import {
  classifyEmail, draftReply, approveDraft, fetchEmail,
  markAsRead, fetchThread, sendReply, getAttachmentUrl,
  extractActionItems, updateActionItem, request,
  deleteCalendarEvent, composeEmail
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
// ---- Attachment helpers (appended) ----------------------------------------
function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}
function getFileTypeInfo(filename, contentType) {
    const ext = (filename.split('.').pop() || '').toLowerCase();
    const ct = (contentType || '').toLowerCase();
    if (ct.startsWith('image/') || ['png','jpg','jpeg','gif','bmp','webp','svg','ico','tiff'].includes(ext))
        return { type: 'image', icon: '🖼️', color: '#8b5cf6', label: ext.toUpperCase() };
    if (ct === 'application/pdf' || ext === 'pdf')
        return { type: 'pdf', icon: '📄', color: '#ef4444', label: 'PDF' };
    if (['doc','docx','odt','rtf'].includes(ext) || ct.includes('word'))
        return { type: 'doc', icon: '📝', color: '#2563eb', label: ext.toUpperCase() };
    if (['xls','xlsx','csv','ods'].includes(ext) || ct.includes('spreadsheet') || ct.includes('excel'))
        return { type: 'sheet', icon: '📊', color: '#16a34a', label: ext.toUpperCase() };
    if (['ppt','pptx','odp'].includes(ext) || ct.includes('presentation'))
        return { type: 'slides', icon: '📽️', color: '#ea580c', label: ext.toUpperCase() };
    if (['zip','rar','7z','tar','gz','bz2','xz'].includes(ext) || ct.includes('zip') || ct.includes('compressed'))
        return { type: 'archive', icon: '📦', color: '#a16207', label: ext.toUpperCase() };
    if (ct.startsWith('video/') || ['mp4','avi','mov','mkv','webm','wmv'].includes(ext))
        return { type: 'video', icon: '🎬', color: '#7c3aed', label: ext.toUpperCase() };
    if (ct.startsWith('audio/') || ['mp3','wav','ogg','flac','aac','m4a'].includes(ext))
        return { type: 'audio', icon: '🎵', color: '#db2777', label: ext.toUpperCase() };
    if (['js','ts','py','java','cpp','c','h','html','css','json','xml','yml','yaml','md','txt','log','sh','bat'].includes(ext) || ct.startsWith('text/'))
        return { type: 'code', icon: '📋', color: '#6366f1', label: ext.toUpperCase() || 'TXT' };
    return { type: 'file', icon: '📎', color: '#6b7280', label: ext.toUpperCase() || 'FILE' };
}
function AttachmentsBar({ attachments, emailId }) {
    const [previewUrl, setPreviewUrl] = useState(null);
    const [previewName, setPreviewName] = useState('');
    if (!attachments || attachments.length === 0) return null;
    const totalSize = attachments.reduce((sum, att) => sum + (att.size || 0), 0);
    const handlePreview = (att) => {
        const info = getFileTypeInfo(att.filename, att.content_type);
        if (info.type === 'image' && att.stored_path) {
            setPreviewUrl(getAttachmentUrl(emailId, att.filename));
            setPreviewName(att.filename);
        }
    };
    const handleDownloadAll = () => {
        attachments.forEach((att, idx) => {
            if (att.stored_path) {
                setTimeout(() => {
                    const a = document.createElement('a');
                    a.href = getAttachmentUrl(emailId, att.filename);
                    a.download = att.filename;
                    a.click();
                }, idx * 300);
            }
        });
    };
    return (
        <>
            <div className="attachments-section">
                <div className="attachments-header">
                    <div className="attachments-header-left">
                        <Paperclip size={14} />
                        <span className="attachments-count">
                            {attachments.length} {attachments.length === 1 ? 'Attachment' : 'Attachments'}
                        </span>
                        {totalSize > 0 && (
                            <span className="attachments-total-size">({formatFileSize(totalSize)})</span>
                        )}
                    </div>
                    {attachments.length > 1 && (
                        <button className="attachments-download-all" onClick={handleDownloadAll} title="Download all attachments">
                            <Download size={13} /> Download all
                        </button>
                    )}
                </div>
                <div className="attachments-grid">
                    {attachments.map((att, idx) => {
                        const info = getFileTypeInfo(att.filename, att.content_type);
                        const isPreviewable = info.type === 'image' && att.stored_path;
                        const downloadUrl = att.stored_path ? getAttachmentUrl(emailId, att.filename) : null;
                        return (
                            <div key={idx} className="attachment-card" title={att.filename}>
                                <div
                                    className={`attachment-card-preview ${isPreviewable ? 'attachment-card-clickable' : ''}`}
                                    style={{ '--att-color': info.color }}
                                    onClick={() => isPreviewable && handlePreview(att)}
                                >
                                    {isPreviewable ? (
                                        <img
                                            src={getAttachmentUrl(emailId, att.filename)}
                                            alt={att.filename}
                                            className="attachment-thumbnail"
                                            onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }}
                                        />
                                    ) : null}
                                    <div className="attachment-card-icon" style={{ display: isPreviewable ? 'none' : 'flex' }}>
                                        <span className="attachment-emoji">{info.icon}</span>
                                        <span className="attachment-type-label" style={{ color: info.color }}>{info.label}</span>
                                    </div>
                                </div>
                                <div className="attachment-card-info">
                                    <span className="attachment-card-name" title={att.filename}>{att.filename}</span>
                                    <div className="attachment-card-meta">
                                        {att.size > 0 && <span className="attachment-card-size">{formatFileSize(att.size)}</span>}
                                        {downloadUrl ? (
                                            <a className="attachment-card-download" href={downloadUrl} download={att.filename} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} title={`Download ${att.filename}`}>
                                                <Download size={12} />
                                            </a>
                                        ) : (
                                            <span className="attachment-card-unavailable" title="File not saved to disk">—</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
            {previewUrl && (
                <div className="attachment-lightbox" onClick={() => setPreviewUrl(null)}>
                    <div className="attachment-lightbox-content" onClick={(e) => e.stopPropagation()}>
                        <div className="attachment-lightbox-header">
                            <span className="attachment-lightbox-name">{previewName}</span>
                            <div className="attachment-lightbox-actions">
                                <a className="btn btn-secondary attachment-lightbox-download" href={previewUrl} download={previewName} target="_blank" rel="noopener noreferrer">
                                    <Download size={14} /> Download
                                </a>
                                <button className="btn btn-secondary" onClick={() => setPreviewUrl(null)}>✕ Close</button>
                            </div>
                        </div>
                        <img src={previewUrl} alt={previewName} className="attachment-lightbox-img" />
                    </div>
                </div>
            )}
        </>
    );
}
function PipelineTrace({ email, classification: cls, draft }) {
    const [open, setOpen] = useState(false);
    if (!cls) return null;

    const piiTypes = draft?.redacted_types || [];
    const hasPii = draft?.pii_redacted || piiTypes.length > 0;
    const isRuleEngineResult = cls.reasoning?.startsWith('Rule engine:');

    const steps = [
        {
            name: 'Email Ingestion',
            status: 'done',
            detail: `Source: ${email.account_id || 'mock'} · ${email.storage_origin || 'source'}`,
            color: '#6366f1',
        },
        {
            name: 'Rule Engine',
            status: 'done',
            detail: isRuleEngineResult ? `Matched — ${cls.reasoning.replace('Rule engine: ', '')}` : 'No rule match → forwarded to LLM',
            color: isRuleEngineResult ? '#f59e0b' : '#6b7280',
        },
        {
            name: 'PII Masking',
            status: 'done',
            detail: hasPii ? `Detected: ${piiTypes.join(', ')}` : 'No PII detected in this email',
            color: hasPii ? '#ef4444' : '#22c55e',
        },
        {
            name: 'AI Classification',
            status: 'done',
            detail: `${cls.priority} / ${cls.category} · ${(cls.confidence * 100).toFixed(0)}% confidence`,
            color: cls.priority === 'critical' ? '#ef4444' : cls.priority === 'high' ? '#f97316' : '#6366f1',
        },
        {
            name: 'Draft Generation',
            status: draft ? 'done' : 'pending',
            detail: draft ? `Quality: ${draft.quality || 'balanced'} · PII shield: ${draft.pii_redacted ? 'active' : 'clean'}` : 'Not yet generated',
            color: draft ? '#10b981' : '#6b7280',
        },
    ];

    return (
        <div className="pipeline-trace">
            <button className="pipeline-trace-toggle" onClick={() => setOpen(!open)}>
                <div className="pipeline-trace-toggle-left">
                    <Sparkles size={12} />
                    <span>AI Pipeline Trace</span>
                    <span className="pipeline-trace-count">{steps.filter(s => s.status === 'done').length}/{steps.length} steps</span>
                </div>
                {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {open && (
                <div className="pipeline-trace-body animate-slide-up">
                    {steps.map((step, i) => (
                        <div key={i} className={`pipeline-step pipeline-step-${step.status}`}>
                            <div className="pipeline-step-indicator" style={{ background: step.status === 'done' ? step.color : 'var(--border)' }}>
                                {step.status === 'done' ? <Check size={10} /> : <span className="pipeline-step-num">{i + 1}</span>}
                            </div>
                            {i < steps.length - 1 && (
                                <div className="pipeline-step-line" style={{ background: steps[i + 1].status === 'done' ? steps[i + 1].color + '40' : 'var(--border)' }} />
                            )}
                            <div className="pipeline-step-content">
                                <span className="pipeline-step-name">{step.name}</span>
                                <span className="pipeline-step-detail">{step.detail}</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
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
                    <AttachmentsBar attachments={msg.attachments} emailId={msg.id} />
                </div>
            )}
        </div>
    );
}
const getConflictingEmailId = (eventId) => {
    if (!eventId) return null;
    if (eventId.startsWith('auto-')) {
        return eventId.replace('auto-', '');
    }
    return null;
};
function EmailDetail({ email, onUpdate, onReload, onSelect, autoDraft, clearAutoDraft }) {
    const [busy, setBusy] = useState(null);
    const [toast, setToast] = useState(null);
    const [draftQuality, setDraftQuality] = useState('balanced');
    const [editedDraft, setEditedDraft] = useState(null);
    const [showQuality, setShowQuality] = useState(false);
    const [whiteMode, setWhiteMode] = useState(false);
    const [sendReschedule, setSendReschedule] = useState(false);
    const [conflictEventUnscheduled, setConflictEventUnscheduled] = useState(false);
    const [rescheduleSent, setRescheduleSent] = useState(false);
    const [sendingReschedule, setSendingReschedule] = useState(false);
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
    // Action items state
    const [actionItems, setActionItems] = useState([]);
    const [loadingActions, setLoadingActions] = useState(false);
    // Multi-draft state
    const [selectedDraftIdx, setSelectedDraftIdx] = useState(0);
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
        setSendReschedule(false);
        setConflictEventUnscheduled(false);
        setRescheduleSent(false);
        setSendingReschedule(false);
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
    useEffect(() => {
        if (autoDraft && email && !busy) {
            handleDraft();
            if (clearAutoDraft) clearAutoDraft();
        }
    }, [autoDraft, email?.id]);
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
    const isOutlook = email.account_id === 'outlook';
    // Outlook emails use the raw Graph ID (strip 'outlook:' prefix)
    const graphId = isOutlook ? email.id.replace(/^outlook:/, '') : null;
    const handleClassify = async () => {
        setBusy('classify');
        try {
            if (isOutlook) {
                const result = await request('/graph/mail/classify', {
                    method: 'POST',
                    body: JSON.stringify({ message_id: graphId }),
                });
                // Apply classification to the local email object
                onUpdate({ ...email, classification: result.classification || result });
            } else {
                await classifyEmail(email.id);
                const updated = await fetchEmail(email.id);
                onUpdate(updated);
            }
            showToast('Classified successfully');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };
    async function handleDraft() {
        setBusy('draft');
        try {
            if (isOutlook) {
                const result = await request('/graph/mail/draft-reply', {
                    method: 'POST',
                    body: JSON.stringify({ message_id: graphId, quality: draftQuality }),
                });
                const draftBody = result.draft_reply?.body || result.body || result.draft || '';
                onUpdate({ ...email, draft_reply: result.draft_reply || { body: draftBody, quality: draftQuality } });
                setEditedDraft(null);
                if (draftBody) {
                    setReplyAction('reply');
                    setReplyTo(email.sender);
                    setReplyBody(draftBody);
                    setShowReply(true);
                    setTimeout(() => replyRef.current?.focus(), 100);
                }
            } else {
                await draftReply(email.id, draftQuality);
                const updated = await fetchEmail(email.id);
                onUpdate(updated);
                setEditedDraft(null);
                if (updated.draft_reply) {
                    setReplyAction('reply');
                    setReplyTo(email.sender);
                    setReplyBody(updated.draft_reply.body);
                    setShowReply(true);
                    setTimeout(() => replyRef.current?.focus(), 100);
                }
            }
            showToast('AI draft generated');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    }
    const handleApprove = async () => {
        setBusy('approve');
        try {
            // Sort thread by timestamp to guarantee we get the absolute newest message
            const sortedThread = [...thread].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            const latestReceived = sortedThread.reverse().find(m => !m.is_sent);
            const replyTargetId = latestReceived?.id || email.id;
            const result = await approveDraft(replyTargetId, sendReschedule);
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
            if (result.reschedule_sent) {
                showToast('Approved! Reply and Reschedule Request sent successfully! ✉️📅');
            } else {
                showToast('Reply sent successfully! ✉️');
            }
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
                {/* Explanation pills */}
                {cls?.explanation_factors?.length > 0 && (
                    <div className="explanation-pills">
                        <Info size={12} className="explanation-icon" />
                        {cls.explanation_factors.map((f, i) => (
                            <span key={i} className="explanation-pill">{f}</span>
                        ))}
                    </div>
                )}
                {/* AI Pipeline Trace — collapsible observability panel */}
                {cls && (
                    <PipelineTrace email={email} classification={cls} draft={draft} />
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
                {cls && (
                    <button className="btn btn-action" onClick={async () => {
                        setLoadingActions(true);
                        try {
                            const items = await extractActionItems(email.id);
                            setActionItems(items);
                            showToast(items.length ? `${items.length} action(s) found` : 'No action items', items.length ? 'success' : 'info');
                        } catch (e) { showToast(e.message, 'error'); }
                        finally { setLoadingActions(false); }
                    }} disabled={loadingActions || !!busy}>
                        {loadingActions ? <><RotateCcw size={14} className="spin" /> Extracting...</> : <><ListChecks size={14} /> Extract Actions</>}
                    </button>
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
                        <AttachmentsBar attachments={email.attachments} emailId={email.id} />
                    </div>
                )}
                {/* Conflict Alert (if conflict exists, whether draft exists or not) */}
                {(() => {
                    if (!cls || !cls.conflicting_event_id || conflictEventUnscheduled) return null;
                    if (draft && draft.conflict_reschedule_draft) return null; // shown in draft section instead
                    const priorityScale = { 'critical': 4, 'high': 3, 'normal': 2, 'low': 1 };
                    const currentWeight = priorityScale[cls.priority] || 2;
                    const conflictWeight = priorityScale[cls.conflicting_event_priority || 'normal'] || 2;
                    const isOverride = currentWeight > conflictWeight;

                    return (
                        <div className="conflict-alert-panel animate-slide-up" style={{
                            margin: '15px 0',
                            padding: '16px',
                            border: `1px solid ${isOverride ? 'rgba(239, 68, 68, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
                            borderRadius: 'var(--radius-md)',
                            background: isOverride ? 'rgba(239, 68, 68, 0.05)' : 'rgba(245, 158, 11, 0.05)',
                            color: 'var(--text-primary)',
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                                <CalendarX size={18} style={{ color: isOverride ? '#ef4444' : '#f59e0b' }} />
                                <h4 style={{ margin: 0, color: isOverride ? '#ef4444' : '#f59e0b', fontSize: '13px', fontWeight: '700' }}>
                                    {isOverride ? 'Conflict Detected: Overlap with Low-Priority Commitment' : 'Conflict Detected: Overlap with Higher-Priority Commitment'}
                                </h4>
                            </div>
                            <p style={{ fontSize: '12px', margin: '0 0 12px 0', color: 'var(--text-secondary)' }}>
                                {isOverride 
                                    ? 'This urgent email conflicts with your existing calendar event. You can unschedule the conflicting event directly or generate a draft reply with a reschedule request.'
                                    : 'This email conflicts with an existing higher-priority commitment on your calendar. You can generate a draft reply to politely ask the sender of this email to reschedule.'}
                            </p>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                {isOverride && (
                                    <button
                                        className="unschedule-btn"
                                        onClick={async () => {
                                            try {
                                                setBusy('unscheduling');
                                                await deleteCalendarEvent(cls.conflicting_event_id);
                                                setConflictEventUnscheduled(true);
                                                showToast('Successfully unscheduled the conflicting casual event! 📅❌');
                                                if (onReload) onReload();
                                            } catch (err) {
                                                showToast(`Failed to unschedule event: ${err.message || err}`, 'error');
                                            } finally {
                                                setBusy(null);
                                            }
                                        }}
                                        disabled={busy !== null}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '6px',
                                            padding: '8px 16px',
                                            fontSize: '11px',
                                            fontWeight: '600',
                                            borderRadius: '4px',
                                            border: '1px solid #ef4444',
                                            background: 'rgba(239, 68, 68, 0.05)',
                                            color: '#ef4444',
                                            cursor: 'pointer',
                                            transition: 'all 0.2s',
                                        }}
                                    >
                                        <CalendarX size={12} />
                                        Unschedule Conflicting Event
                                    </button>
                                )}
                                
                                {isOverride ? (
                                    <button
                                        className="btn-resched-select-lower"
                                        onClick={() => {
                                            const targetId = getConflictingEmailId(cls.conflicting_event_id);
                                            if (targetId) {
                                                onSelect(targetId, { autoDraft: true });
                                                showToast('Opening conflicting lower-priority email to draft reschedule request...');
                                            } else {
                                                showToast('Could not find conflicting email to reschedule', 'error');
                                            }
                                        }}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '6px',
                                            padding: '8px 16px',
                                            fontSize: '11px',
                                            fontWeight: '600',
                                            borderRadius: '4px',
                                            border: '1px solid #f59e0b',
                                            background: '#f59e0b',
                                            color: '#1e1b4b',
                                            cursor: 'pointer',
                                            transition: 'all 0.2s',
                                        }}
                                    >
                                        <Reply size={12} />
                                        Reschedule Conflicting Event
                                    </button>
                                ) : (
                                    <button
                                        className="btn-draft-direct"
                                        onClick={handleDraft}
                                        disabled={busy !== null}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '6px',
                                            padding: '8px 16px',
                                            fontSize: '11px',
                                            fontWeight: '600',
                                            borderRadius: '4px',
                                            border: '1px solid #f59e0b',
                                            background: '#f59e0b',
                                            color: '#1e1b4b',
                                            cursor: 'pointer',
                                            transition: 'all 0.2s',
                                        }}
                                    >
                                        <Sparkles size={12} />
                                        Generate AI Reschedule Reply
                                    </button>
                                )}
                            </div>
                        </div>
                    );
                })()}
                {/* AI Draft (shown if draft exists but reply not open) */}
                {draft && !showReply && (
                    <div className="detail-draft animate-slide-up">
                        <div className="draft-header">
                            <h3 className="draft-title">
                                <Sparkles size={14} /> AI Draft Reply
                                <span className="draft-quality-badge">{draft.quality || draftQuality}</span>
                            </h3>
                            {/* Multi-draft selector tabs */}
                            {draft.alternatives?.length > 0 && (
                                <div className="draft-variant-tabs">
                                    <button className={`draft-variant-tab ${selectedDraftIdx === 0 ? 'active' : ''}`}
                                        onClick={() => { setSelectedDraftIdx(0); setEditedDraft(null); }}>
                                        Professional
                                    </button>
                                    {draft.alternatives.map((_, i) => (
                                        <button key={i} className={`draft-variant-tab ${selectedDraftIdx === i + 1 ? 'active' : ''}`}
                                            onClick={() => { setSelectedDraftIdx(i + 1); setEditedDraft(null); }}>
                                            {i === 0 ? 'Concise' : 'Warm'}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                        {draft.pii_redacted && (
                            <div className="draft-pii-warning">
                                <Shield size={13} />
                                PII protected: {draft.redacted_types.join(', ')}
                            </div>
                        )}
                        <textarea
                            className="draft-editor"
                            value={editedDraft !== null ? editedDraft : (selectedDraftIdx === 0 ? draft.body : (draft.alternatives?.[selectedDraftIdx - 1] || draft.body))}
                            onChange={(e) => setEditedDraft(e.target.value)}
                            rows={6}
                        />
                        {draft.conflict_reschedule_draft && (() => {
                            const isOverrideDraft = draft.conflict_reschedule_draft.type !== 'yield';
                            return (
                                <div className="reschedule-draft-box animate-slide-up" style={{
                                    margin: '10px 0',
                                    padding: '12px',
                                    border: '1px solid rgba(245, 158, 11, 0.3)',
                                    borderRadius: 'var(--radius-md)',
                                    background: 'rgba(245, 158, 11, 0.05)',
                                    color: 'var(--text-primary)',
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                                        {isOverrideDraft && (
                                            <input
                                                type="checkbox"
                                                id="send-reschedule-checkbox"
                                                checked={sendReschedule}
                                                onChange={(e) => setSendReschedule(e.target.checked)}
                                                disabled={conflictEventUnscheduled}
                                                style={{ marginTop: '3px', cursor: conflictEventUnscheduled ? 'not-allowed' : 'pointer' }}
                                            />
                                        )}
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            {isOverrideDraft ? (
                                                <label htmlFor="send-reschedule-checkbox" style={{
                                                    fontSize: '12px',
                                                    fontWeight: '600',
                                                    color: conflictEventUnscheduled ? 'var(--text-muted)' : '#f59e0b',
                                                    cursor: conflictEventUnscheduled ? 'not-allowed' : 'pointer',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '4px'
                                                }}>
                                                    <CalendarPlus size={13} />
                                                    Conflict detected: Reschedule low-priority commitment?
                                                </label>
                                            ) : (
                                                <label style={{
                                                    fontSize: '12px',
                                                    fontWeight: '600',
                                                    color: '#f59e0b',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '4px',
                                                    marginBottom: '4px'
                                                }}>
                                                    <CalendarPlus size={13} />
                                                    Conflict detected: Reschedule this lower-priority commitment?
                                                </label>
                                            )}
                                            <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                                                {isOverrideDraft 
                                                    ? <>Politely ask <strong>{draft.conflict_reschedule_draft.recipient}</strong> to reschedule <em>"{draft.conflict_reschedule_draft.event_title}"</em>.</>
                                                    : <>Politely ask <strong>{draft.conflict_reschedule_draft.recipient}</strong> to reschedule <em>"{draft.conflict_reschedule_draft.event_title}"</em> (this meeting).</>}
                                            </div>
                                            <div style={{
                                                fontSize: '11px',
                                                color: 'var(--text-secondary)',
                                                background: 'rgba(0,0,0,0.25)',
                                                padding: '8px',
                                                borderRadius: 'var(--radius-sm)',
                                                marginTop: '6px',
                                                fontFamily: 'var(--font-mono)',
                                                whiteSpace: 'pre-wrap',
                                                borderLeft: '2.5px solid #f59e0b'
                                            }}>
                                                <strong>Subject:</strong> {draft.conflict_reschedule_draft.subject}<br/><br/>
                                                {draft.conflict_reschedule_draft.body}
                                            </div>

                                            <div style={{
                                                display: 'flex',
                                                gap: '8px',
                                                marginTop: '12px',
                                                flexWrap: 'wrap'
                                            }}>
                                                {isOverrideDraft ? (
                                                    <>
                                                        <button
                                                            className="unschedule-btn"
                                                            onClick={async () => {
                                                                try {
                                                                    setBusy('unscheduling');
                                                                    await deleteCalendarEvent(draft.conflict_reschedule_draft.event_id);
                                                                    setConflictEventUnscheduled(true);
                                                                    setSendReschedule(false);
                                                                    showToast('Successfully unscheduled the conflicting casual event! 📅❌');
                                                                    if (onReload) onReload();
                                                                } catch (err) {
                                                                    showToast(`Failed to unschedule event: ${err.message || err}`, 'error');
                                                                } finally {
                                                                    setBusy(null);
                                                                }
                                                            }}
                                                            disabled={conflictEventUnscheduled || busy !== null}
                                                            style={{
                                                                display: 'flex',
                                                                alignItems: 'center',
                                                                gap: '6px',
                                                                padding: '6px 12px',
                                                                fontSize: '11px',
                                                                fontWeight: '600',
                                                                borderRadius: '4px',
                                                                border: '1px solid #ef4444',
                                                                background: conflictEventUnscheduled ? 'rgba(239, 68, 68, 0.1)' : 'rgba(239, 68, 68, 0.05)',
                                                                color: '#ef4444',
                                                                cursor: conflictEventUnscheduled ? 'not-allowed' : 'pointer',
                                                                transition: 'all 0.2s',
                                                                opacity: conflictEventUnscheduled ? 0.6 : 1
                                                            }}
                                                        >
                                                            <CalendarX size={12} />
                                                            {conflictEventUnscheduled ? 'Event Unscheduled' : 'Unschedule Conflicting Event'}
                                                        </button>

                                                        <button
                                                            className="btn-resched-select-lower"
                                                            onClick={() => {
                                                                const targetId = getConflictingEmailId(draft.conflict_reschedule_draft.event_id);
                                                                if (targetId) {
                                                                    onSelect(targetId, { autoDraft: true });
                                                                    showToast('Opening conflicting lower-priority email to draft reschedule request...');
                                                                } else {
                                                                    showToast('Could not find conflicting email to reschedule', 'error');
                                                                }
                                                            }}
                                                            style={{
                                                                display: 'flex',
                                                                alignItems: 'center',
                                                                gap: '6px',
                                                                padding: '6px 12px',
                                                                fontSize: '11px',
                                                                fontWeight: '600',
                                                                borderRadius: '4px',
                                                                border: '1px solid #f59e0b',
                                                                background: '#f59e0b',
                                                                color: '#1e1b4b',
                                                                cursor: 'pointer',
                                                                transition: 'all 0.2s',
                                                            }}
                                                        >
                                                            <Reply size={12} />
                                                            Reschedule Conflicting Event
                                                        </button>
                                                    </>
                                                ) : (
                                                    <button
                                                        className="send-resched-direct-btn"
                                                        onClick={async () => {
                                                            try {
                                                                setSendingReschedule(true);
                                                                await composeEmail(
                                                                    [draft.conflict_reschedule_draft.recipient],
                                                                    [],
                                                                    [],
                                                                    draft.conflict_reschedule_draft.subject,
                                                                    draft.conflict_reschedule_draft.body,
                                                                    email.account_id || 'mock'
                                                                );
                                                                setRescheduleSent(true);
                                                                showToast('Reschedule request sent successfully! ✉️');
                                                                try {
                                                                    await deleteCalendarEvent(draft.conflict_reschedule_draft.event_id);
                                                                    setConflictEventUnscheduled(true);
                                                                    if (onReload) onReload();
                                                                } catch (delErr) {
                                                                    console.error("Failed to delete event after reschedule send:", delErr);
                                                                }
                                                            } catch (err) {
                                                                showToast(`Failed to send email: ${err.message || err}`, 'error');
                                                            } finally {
                                                                setSendingReschedule(false);
                                                            }
                                                        }}
                                                        disabled={rescheduleSent || sendingReschedule}
                                                        style={{
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            gap: '6px',
                                                            padding: '6px 12px',
                                                            fontSize: '11px',
                                                            fontWeight: '600',
                                                            borderRadius: '4px',
                                                            border: '1px solid #f59e0b',
                                                            background: rescheduleSent ? 'rgba(245, 158, 11, 0.1)' : '#f59e0b',
                                                            color: rescheduleSent ? '#f59e0b' : '#1e1b4b',
                                                            cursor: rescheduleSent ? 'not-allowed' : 'pointer',
                                                            transition: 'all 0.2s',
                                                            opacity: rescheduleSent ? 0.6 : 1
                                                        }}
                                                    >
                                                        <Send size={12} />
                                                        {rescheduleSent ? 'Reschedule Sent' : sendingReschedule ? 'Sending...' : 'Send Reschedule Request'}
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })()}
                        <div className="draft-footer">
                            <span className="draft-hint" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Sparkles size={11} style={{ opacity: 0.8 }} /> AI responses can make mistakes. Verify before sending.
                            </span>
                            <div className="draft-pii-shield">
                                <Shield size={12} />
                                PII Shield Active
                            </div>
                        </div>
                    </div>
                )}
                {/* Action Items Panel */}
                {actionItems.length > 0 && (
                    <div className="action-items-panel animate-slide-up">
                        <div className="action-items-header">
                            <h3 className="action-items-title"><ListChecks size={14} /> Action Items</h3>
                            <span className="action-items-count">{actionItems.filter(a => a.status === 'pending').length} pending</span>
                        </div>
                        <div className="action-items-list">
                            {actionItems.map(item => {
                                const isOverdue = item.due_date && item.status === 'pending' && new Date(item.due_date) < new Date();
                                return (
                                <div key={item.id} className={`action-item action-item-${item.status}`}
                                  style={{borderLeft: `3px solid ${item.priority === 'high' ? '#ef4444' : item.priority === 'low' ? '#6b7280' : '#6366f1'}`}}>
                                    <div className="action-item-content">
                                        <span className="action-item-desc">{item.description}</span>
                                        <div style={{display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginTop: '4px'}}>
                                            {item.priority && item.priority !== 'normal' && (
                                                <span style={{
                                                    fontSize: '10px', fontWeight: 700, padding: '1px 6px',
                                                    borderRadius: '999px', textTransform: 'uppercase',
                                                    background: item.priority === 'high' ? 'rgba(239,68,68,0.12)' : 'rgba(107,114,128,0.12)',
                                                    color: item.priority === 'high' ? '#ef4444' : '#6b7280',
                                                }}>{item.priority}</span>
                                            )}
                                            {isOverdue && (
                                                <span style={{
                                                    fontSize: '10px', fontWeight: 700, padding: '1px 6px',
                                                    borderRadius: '999px', background: 'rgba(239,68,68,0.12)',
                                                    color: '#ef4444', animation: 'pulse-soft 2s infinite',
                                                }}>⚠ OVERDUE</span>
                                            )}
                                            {item.due_date && !isOverdue && (
                                                <span className="action-item-due">
                                                    <Clock size={11} /> {new Date(item.due_date).toLocaleDateString()}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="action-item-actions">
                                        {item.status === 'pending' && (
                                            <>
                                                <button className="action-item-btn action-item-complete"
                                                    title="Mark complete"
                                                    onClick={async () => {
                                                        await updateActionItem(item.id, 'completed');
                                                        setActionItems(prev => prev.map(a => a.id === item.id ? {...a, status: 'completed'} : a));
                                                    }}>
                                                    <CheckCircle size={14} />
                                                </button>
                                                <button className="action-item-btn action-item-dismiss"
                                                    title="Dismiss"
                                                    onClick={async () => {
                                                        await updateActionItem(item.id, 'dismissed');
                                                        setActionItems(prev => prev.map(a => a.id === item.id ? {...a, status: 'dismissed'} : a));
                                                    }}>
                                                    <XCircle size={14} />
                                                </button>
                                            </>
                                        )}
                                        {item.status === 'completed' && (
                                            <span className="action-item-status-badge completed"><Check size={12} /> Done</span>
                                        )}
                                        {item.status === 'dismissed' && (
                                            <span className="action-item-status-badge dismissed">Dismissed</span>
                                        )}
                                    </div>
                                </div>
                                );
                            })}
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
                            <div style={{ flex: 1, display: 'flex', alignItems: 'center', paddingLeft: '12px' }}>
                                <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                    <Sparkles size={11} style={{ opacity: 0.7 }} /> AI responses can make mistakes.
                                </span>
                            </div>
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
