/**
 * Format an ISO timestamp into a short, readable date string.
 * Shows time if today, "Yesterday" if yesterday, otherwise "May 7".
 */
export function formatDate(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;
    const oneDay = 86400000;

    if (diff < oneDay && date.getDate() === now.getDate()) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    if (diff < 2 * oneDay) {
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (date.getDate() === yesterday.getDate()) {
            return 'Yesterday';
        }
    }

    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/**
 * Extract a short display name from an email address.
 * "alice.smith@company.com" -> "Alice Smith"
 * "noreply@techdigest.io" -> "noreply@techdigest.io"
 */
export function formatSender(email) {
    const local = email.split('@')[0];
    // If it looks like a real name (has dots or underscores), format it
    if (/[._-]/.test(local) && local !== 'noreply' && local !== 'no-reply') {
        return local
            .split(/[._-]/)
            .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
            .join(' ');
    }
    return email;
}

/**
 * Generate a deterministic HSL color from a sender's email address.
 * Used for avatar backgrounds.
 */
export function senderColor(email) {
    let hash = 0;
    for (let i = 0; i < email.length; i++) {
        hash = email.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hue = Math.abs(hash) % 360;
    return `hsl(${hue}, 55%, 45%)`;
}

/**
 * Format a full date-time for display in detail views.
 */
export function formatFullDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleDateString([], {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}
