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

export function classifyEmail(id) {
    return request(`/emails/${id}/classify`, { method: 'POST' });
}

export function draftReply(id, quality = 'balanced') {
    return request(`/emails/${id}/draft`, {
        method: 'POST',
        body: JSON.stringify({ quality }),
    });
}

export function approveDraft(id) {
    return request(`/emails/${id}/approve`, { method: 'POST' });
}

export function classifyAll() {
    return request('/emails/classify-all', { method: 'POST' });
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
