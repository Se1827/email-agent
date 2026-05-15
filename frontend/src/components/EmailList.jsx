import { Star } from 'lucide-react';
import { formatDate, formatSender, senderColor } from '../utils';
import { toggleStar, fetchEmail } from '../api';
import './EmailList.css';

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

    return (
        <div className="email-list" id="email-list">
            <div className="email-list-header">
                <span className="email-list-count">{emails.length} emails</span>
            </div>
            <div className="email-list-items">
                {emails.map((email) => {
                    const cls = email.classification;
                    const isSelected = selected?.id === email.id;
                    const isUnread = !email.is_read && !cls;

                    return (
                        <div
                            key={email.id}
                            className={`email-row ${isSelected ? 'email-row-selected' : ''} ${isUnread ? 'email-row-unread' : ''}`}
                            onClick={() => onSelect(email)}
                        >
                            {/* Avatar */}
                            <div className="email-avatar" style={{ background: senderColor(email.sender) }}>
                                {formatSender(email.sender).charAt(0).toUpperCase()}
                            </div>

                            <div className="email-row-content">
                                <div className="email-row-top">
                                    <span className="email-sender">{formatSender(email.sender)}</span>
                                    <div className="email-row-top-right">
                                        {cls && <span className={`priority-pip priority-${cls.priority}`} />}
                                        <span className="email-date">{formatDate(email.timestamp)}</span>
                                    </div>
                                </div>
                                <div className="email-subject">{email.subject}</div>
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
                                className={`email-star-btn ${email.is_starred ? 'starred' : ''}`}
                                onClick={(e) => handleStar(e, email)}
                                title={email.is_starred ? 'Unstar' : 'Star'}
                            >
                                <Star size={14} fill={email.is_starred ? '#fbbf24' : 'none'} />
                            </button>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default EmailList;
