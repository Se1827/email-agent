import { Star, MessageSquare } from 'lucide-react';
import { formatDate, formatSender, senderColor } from '../utils';
import { toggleStar, fetchEmail } from '../api';
import './EmailList.css';

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
                                <div className="email-avatar-stack">
                                    {group.participants.slice(0, 2).map((p, i) => (
                                        <div
                                            key={p}
                                            className="email-avatar email-avatar-stacked"
                                            style={{
                                                background: senderColor(p),
                                                zIndex: 2 - i,
                                            }}
                                        >
                                            {formatSender(p).charAt(0).toUpperCase()}
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="email-avatar" style={{ background: senderColor(email.sender) }}>
                                    {formatSender(email.sender).charAt(0).toUpperCase()}
                                </div>
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
                                    {group.hasSent && <span className="sent-indicator">↩</span>}
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
