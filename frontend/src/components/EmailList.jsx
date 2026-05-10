import { formatDate, formatSender } from '../utils';
import './EmailList.css';

const PRIORITY_LABELS = {
    critical: 'CRT',
    high: 'HI',
    normal: 'NRM',
    low: 'LO',
};

function EmailList({ emails, selected, onSelect, loading }) {
    if (loading) {
        return (
            <div className="email-list">
                <div className="email-list-empty">Loading emails...</div>
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

    return (
        <div className="email-list">
            <div className="email-list-header">
                <span className="email-list-count">{emails.length} emails</span>
            </div>
            <div className="email-list-items">
                {emails.map((email) => {
                    const cls = email.classification;
                    const isSelected = selected?.id === email.id;
                    const isRead = !!cls;

                    return (
                        <div
                            key={email.id}
                            className={`email-row ${isSelected ? 'email-row-selected' : ''} ${!isRead ? 'email-row-unread' : ''
                                }`}
                            onClick={() => onSelect(email)}
                        >
                            {cls && (
                                <span className={`priority-dot priority-${cls.priority}`} />
                            )}
                            {!cls && <span className="priority-dot priority-none" />}

                            <div className="email-row-content">
                                <div className="email-row-top">
                                    <span className="email-sender">{formatSender(email.sender)}</span>
                                    <span className="email-date">{formatDate(email.timestamp)}</span>
                                </div>
                                <div className="email-subject">{email.subject}</div>
                                <div className="email-row-bottom">
                                    <span className="email-snippet">
                                        {email.body.slice(0, 80).replace(/\n/g, ' ')}
                                    </span>
                                    {cls && (
                                        <span className={`category-tag category-${cls.category}`}>
                                            {cls.category}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default EmailList;
