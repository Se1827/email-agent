import { useState } from 'react';
import { classifyEmail, draftReply, approveDraft, fetchEmail } from '../api';
import { formatDate } from '../utils';
import './EmailDetail.css';

function EmailDetail({ email, onUpdate, onReload }) {
    const [busy, setBusy] = useState(null);
    const [toast, setToast] = useState(null);

    if (!email) {
        return (
            <div className="email-detail email-detail-empty">
                <p>Select an email to view its contents.</p>
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
            await draftReply(email.id);
            const updated = await fetchEmail(email.id);
            onUpdate(updated);
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
            showToast('Reply sent (simulated)');
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    const cls = email.classification;
    const draft = email.draft_reply;

    return (
        <div className="email-detail">
            {toast && (
                <div className={`toast toast-${toast.type}`}>{toast.msg}</div>
            )}

            <div className="detail-header">
                <h2 className="detail-subject">{email.subject}</h2>
                <div className="detail-meta">
                    <span className="detail-sender">
                        From: <strong>{email.sender}</strong>
                    </span>
                    <span className="detail-recipients">
                        To: {email.recipients.join(', ')}
                    </span>
                    <span className="detail-date">{formatDate(email.timestamp)}</span>
                </div>

                {cls && (
                    <div className="detail-classification">
                        <span className={`priority-badge priority-${cls.priority}`}>
                            {cls.priority}
                        </span>
                        <span className={`category-badge category-${cls.category}`}>
                            {cls.category}
                        </span>
                        <span className="confidence">
                            {(cls.confidence * 100).toFixed(0)}% confidence
                        </span>
                        {cls.reasoning && (
                            <span className="reasoning">{cls.reasoning}</span>
                        )}
                    </div>
                )}
            </div>

            <div className="detail-actions">
                <button
                    className="btn btn-action"
                    onClick={handleClassify}
                    disabled={!!busy}
                >
                    {busy === 'classify' ? 'Classifying...' : cls ? 'Re-classify' : 'Classify'}
                </button>
                {cls && (
                    <button
                        className="btn btn-action"
                        onClick={handleDraft}
                        disabled={!!busy}
                    >
                        {busy === 'draft' ? 'Drafting...' : draft ? 'Re-draft' : 'Draft Reply'}
                    </button>
                )}
                {draft && (
                    <button
                        className="btn btn-approve"
                        onClick={handleApprove}
                        disabled={!!busy}
                    >
                        {busy === 'approve' ? 'Sending...' : 'Approve & Send'}
                    </button>
                )}
            </div>

            <div className="detail-body">
                <pre className="email-body-text">{email.body}</pre>
            </div>

            {draft && (
                <div className="detail-draft">
                    <h3 className="draft-title">Draft Reply</h3>
                    {draft.pii_redacted && (
                        <div className="draft-pii-warning">
                            PII redacted: {draft.redacted_types.join(', ')}
                        </div>
                    )}
                    <pre className="draft-body-text">{draft.body}</pre>
                </div>
            )}
        </div>
    );
}

export default EmailDetail;
