const API_BASE = '/api';

async function request(path, options = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status}: ${body}`);
    }
    return res.json();
}

// ---- Email ----
export function fetchEmails(accountId) {
    const params = accountId ? `?account_id=${accountId}` : '';
    return request(`/emails${params}`);
}

export function fetchEmail(id) {
    return request(`/emails/${id}`);
}

export function fetchThread(id) {
    return request(`/emails/${id}/thread`);
}

export function classifyEmail(id, force = true) {
    return request(`/emails/${id}/classify?force=${force}`, { method: 'POST' });
}

export function draftReply(id, quality = 'balanced', force = true) {
    return request(`/emails/${id}/draft?force=${force}`, {
        method: 'POST',
        body: JSON.stringify({ quality }),
    });
}

export function approveDraft(id) {
    return request(`/emails/${id}/approve`, { method: 'POST' });
}

export function sendReply(emailId, body, to, cc) {
    return request(`/emails/${emailId}/send-reply`, {
        method: 'POST',
        body: JSON.stringify({ body, to: to || null, cc: cc || null }),
    });
}

export function composeEmail(to, cc, subject, body, accountId) {
    return request('/emails/compose', {
        method: 'POST',
        body: JSON.stringify({ to, cc, subject, body, account_id: accountId }),
    });
}

export function classifyAll(accountId) {
    const params = accountId ? `?account_id=${accountId}` : '';
    return request(`/emails/classify-all${params}`, { method: 'POST' });
}

export function refreshInbox() {
    return request('/emails/refresh', { method: 'POST' });
}

export function toggleStar(id) {
    return request(`/emails/${id}/star`, { method: 'POST' });
}

export function markAsRead(id) {
    return request(`/emails/${id}/read`, { method: 'POST' });
}

// ---- Dashboard ----
export function fetchDashboard() {
    return request('/dashboard');
}

export function fetchNotifications() {
    return request('/notifications');
}

export function dismissNotification(id) {
    return request(`/notifications/${id}/dismiss`, { method: 'POST' });
}

// ---- Accounts ----
export function fetchAccounts() {
    return request('/accounts');
}

export function createAccount(data) {
    return request('/accounts', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export function updateAccount(id, data) {
    return request(`/accounts/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

export function deleteAccount(id) {
    return request(`/accounts/${id}`, { method: 'DELETE' });
}

// ---- Calendar ----
export function fetchCalendarEvents() {
    return request('/calendar');
}

export function fetchUpcomingEvents(days = 7) {
    return request(`/calendar/upcoming?days=${days}`);
}

export function createCalendarEvent(data) {
    return request('/calendar/events', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export function updateCalendarEvent(id, data) {
    return request(`/calendar/events/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

export function deleteCalendarEvent(id) {
    return request(`/calendar/events/${id}`, { method: 'DELETE' });
}

// ---- AI ----
export function askAI(question, contextType, contextId) {
    return request('/ai/ask', {
        method: 'POST',
        body: JSON.stringify({
            question,
            context_type: contextType,
            context_id: contextId,
        }),
    });
}

// ---- Storage ----
export function fetchStorageStats() {
    return request('/storage/stats');
}

