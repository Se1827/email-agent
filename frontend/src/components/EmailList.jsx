import { Star, MessageSquare, Plane, Calendar, CheckCircle2, AlertTriangle, Mail, CreditCard, GitPullRequest, ClipboardList, ShieldAlert, Newspaper, CornerUpLeft } from 'lucide-react';
import { formatDate, formatSender, senderColor, detectScenario } from '../utils';
import { toggleStar, fetchEmail } from '../api';
import './EmailList.css';

function EmailAvatar({ email }) {
    const scenario = detectScenario(email);
    const colors = {
        flight:     { bg: 'rgba(14, 165, 233, 0.12)', fg: '#0ea5e9' },
        meeting:    { bg: 'rgba(167, 139, 250, 0.12)', fg: '#a78bfa' },
        goodnews:   { bg: 'rgba(16, 185, 129, 0.12)', fg: '#10b981' },
        alert:      { bg: 'rgba(245, 158, 11, 0.12)',  fg: '#f59e0b' },
        finance:    { bg: 'rgba(16, 185, 129, 0.12)',  fg: '#10b981' },
        code:       { bg: 'rgba(129, 140, 248, 0.12)', fg: '#818cf8' },
        task:       { bg: 'rgba(244, 63, 94, 0.12)',   fg: '#f43f5e' },
        spam:       { bg: 'rgba(239, 68, 68, 0.12)',   fg: '#ef4444' },
        newsletter: { bg: 'rgba(6, 182, 212, 0.12)',   fg: '#06b6d4' },
        default:    { bg: 'rgba(99, 102, 241, 0.12)',  fg: '#6366f1' },
    };

    const config = colors[scenario] || colors.default;

    const Icon = {
        flight: Plane,
        meeting: Calendar,
        goodnews: CheckCircle2,
        alert: AlertTriangle,
        finance: CreditCard,
        code: GitPullRequest,
        task: ClipboardList,
        spam: ShieldAlert,
        newsletter: Newspaper,
        default: Mail,
    }[scenario] || Mail;

    return (
        <div 
            className="email-avatar-icon" 
            style={{ 
                background: config.bg, 
                color: config.fg, 
                width: 36, 
                height: 36, 
                borderRadius: '50%', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center', 
                flexShrink: 0 
            }}
        >
            <Icon size={16} />
        </div>
    );
}


/**
 * Group emails by thread_id so we show one row per conversation.
 * Each group shows the latest message's preview and the count of messages.
 */
function groupByThread(emails) {
    const threads = new Map();
    for (const email of emails) {
        const tid = email.thread_id || email.id;
        if (!threads.has(tid)) {
            threads.set(tid, []);
        }
        threads.get(tid).push(email);
    }

    const groups = [];
    for (const [tid, msgs] of threads) {
        // Sort by timestamp descending — latest first
        msgs.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        const latest = msgs[0];
        // Collect unique participants
        const participants = [...new Set(msgs.flatMap(m => [m.sender]))];
        // Use the classification of any email in the thread (prefer classified)
        const classified = msgs.find(m => m.classification);

        groups.push({
            id: tid,
            latestEmail: latest,
            count: msgs.length,
            participants,
            classification: classified?.classification || null,
            isStarred: msgs.some(m => m.is_starred),
            isUnread: msgs.some(m => !m.is_read && !m.classification),
            hasDraft: msgs.some(m => m.draft_reply),
            hasSent: msgs.some(m => m.is_sent),
            allEmails: msgs,
        });
    }

    return groups;
}

function EmailList({ emails, selected, onSelect, loading }) {
    if (loading) {
        return (
            <div className="email-list">
                <div className="email-list-loading">
                    {[1,2,3,4,5].map(i => (
                        <div key={i} className="email-row-skeleton shimmer-bg" />
                    ))}
                </div>
            </div>
        );
    }

    if (emails.length === 0) {
        return (
            <div className="email-list">
                <div className="email-list-empty">No emails match the current filters.</div>
            </div>
        );
    }

    const handleStar = async (e, email) => {
        e.stopPropagation();
        try {
            await toggleStar(email.id);
            const updated = await fetchEmail(email.id);
            onSelect(selected?.id === email.id ? updated : selected);
        } catch (_) { /* ignore */ }
    };

    const threadGroups = groupByThread(emails);

    return (
        <div className="email-list" id="email-list">
            <div className="email-list-header">
                <span className="email-list-count">
                    {emails.length} email{emails.length !== 1 ? 's' : ''}
                    {threadGroups.length !== emails.length && (
                        <span className="thread-group-count"> · {threadGroups.length} conversation{threadGroups.length !== 1 ? 's' : ''}</span>
                    )}
                </span>
            </div>
            <div className="email-list-items">
                {threadGroups.map((group) => {
                    const email = group.latestEmail;
                    const cls = group.classification;
                    const isSelected = selected && (
                        selected.id === email.id ||
                        group.allEmails.some(m => m.id === selected.id)
                    );
                    const isUnread = group.isUnread;

                    return (
                        <div
                            key={group.id}
                            className={`email-row ${isSelected ? 'email-row-selected' : ''} ${isUnread ? 'email-row-unread' : ''}`}
                            onClick={() => onSelect(email)}
                        >
                            {/* Avatar */}
                            {group.count > 1 ? (
                                <div className="email-avatar-stack" style={{ position: 'relative', width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <EmailAvatar email={email} />
                                    <span 
                                        className="thread-count-indicator"
                                        style={{
                                            position: 'absolute',
                                            bottom: -2,
                                            right: -2,
                                            background: 'var(--accent)',
                                            color: '#fff',
                                            fontSize: '9px',
                                            fontWeight: 'bold',
                                            borderRadius: '50%',
                                            width: 14,
                                            height: 14,
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            border: '1.5px solid var(--bg-secondary)',
                                            zIndex: 5
                                        }}
                                    >
                                        {group.count}
                                    </span>
                                </div>
                            ) : (
                                <EmailAvatar email={email} />
                            )}

                            <div className="email-row-content">
                                <div className="email-row-top">
                                    <span className="email-sender">
                                        {group.count > 1
                                            ? group.participants.slice(0, 2).map(p => formatSender(p)).join(', ')
                                            : formatSender(email.sender)
                                        }
                                    </span>
                                    <div className="email-row-top-right">
                                        {group.count > 1 && (
                                            <span className="thread-count-pip">
                                                <MessageSquare size={10} />
                                                {group.count}
                                            </span>
                                        )}
                                        {cls && <span className={`priority-pip priority-${cls.priority}`} />}
                                        <span className="email-date">{formatDate(email.timestamp)}</span>
                                    </div>
                                </div>
                                <div className="email-subject">
                                    {email.subject}
                                    {group.hasSent && <span className="sent-indicator"><CornerUpLeft size={10} /></span>}
                                </div>
                                <div className="email-row-bottom">
                                    <span className="email-snippet">
                                        {email.body.slice(0, 90).replace(/\n/g, ' ')}
                                    </span>
                                    <div className="email-row-tags">
                                        {cls && (
                                            <span className={`category-tag category-${cls.category}`}>
                                                {cls.category}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <button
                                className={`email-star-btn ${group.isStarred ? 'starred' : ''}`}
                                onClick={(e) => handleStar(e, email)}
                                title={group.isStarred ? 'Unstar' : 'Star'}
                            >
                                <Star size={14} fill={group.isStarred ? '#fbbf24' : 'none'} />
                            </button>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default EmailList;
