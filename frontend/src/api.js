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

export function fetchEmails() {
    return request('/emails');
}

export function fetchEmail(id) {
    return request(`/emails/${id}`);
}

export function classifyEmail(id) {
    return request(`/emails/${id}/classify`, { method: 'POST' });
}

export function draftReply(id) {
    return request(`/emails/${id}/draft`, { method: 'POST' });
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
