/**
 * api.js — All backend requests go through here.
 * Auth token is pulled from sessionStorage and injected as a Bearer header.
 */

const API_BASE = '/api';

function getToken() {
  return sessionStorage.getItem('email_agent_token');
}

export async function request(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

// ---- Auth ----
export function fetchAuthStatus() {
  return fetch('/api/auth/status').then(r => r.json());
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
export function approveDraft(id, sendReschedule = false) {
  return request(`/emails/${id}/approve?send_reschedule=${sendReschedule}`, { method: 'POST' });
}
export function sendReply(emailId, body, to, cc, bcc, action = 'reply') {
  return request(`/emails/${emailId}/send-reply`, {
    method: 'POST',
    body: JSON.stringify({ body, to: to || null, cc: cc || null, bcc: bcc || null, action }),
  });
}
export function composeEmail(to, cc, bcc, subject, body, accountId) {
  return request('/emails/compose', {
    method: 'POST',
    body: JSON.stringify({ to, cc, bcc, subject, body, account_id: accountId }),
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
export function syncCalendarEvents() {
  return request('/calendar/sync', { method: 'POST' });
}

// ---- AI ----
export function aiComposeEmail(prompt, quality = 'balanced') {
  return request('/emails/ai-compose', {
    method: 'POST',
    body: JSON.stringify({ prompt, quality }),
  });
}
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

// ---- Graph API Configuration ----
export function fetchGraphConfig() {
  return request('/graph/config');
}
export function updateGraphConfig(data) {
  return request('/graph/config', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ---- Attachments ----
export function getAttachmentUrl(emailId, filename) {
  const token = getToken();
  const base = `${API_BASE}/attachments/download?email_id=${encodeURIComponent(emailId)}&filename=${encodeURIComponent(filename)}`;
  return token ? `${base}&auth_token=${encodeURIComponent(token)}` : base;
}
export function fetchAttachments(emailId) {
  return request(`/emails/${emailId}/attachments`);
}

// ---- App Settings ----
export function fetchSettings() {
  return request('/settings');
}
export function saveSettings(data) {
  return request('/settings', { method: 'PUT', body: JSON.stringify(data) });
}

// ---- Storage / Docker Setup ----
export function fetchStorageSetupStatus() {
  return request('/storage/status');
}
export function setupStorage(database_url) {
  return request('/storage/setup', {
    method: 'POST',
    body: JSON.stringify({ database_url }),
  });
}

// ---- Graph Login (device-code, in-browser) ----
export function triggerGraphLogin() {
  return request('/graph/login', { method: 'POST' });
}
export function fetchGraphLoginStatus() {
  return request('/graph/login/status');
}

// ---- AI Mode Settings ----
export function fetchAIMode() {
  return request('/settings/ai-mode');
}
export function updateAIMode(mode) {
  return request('/settings/ai-mode', {
    method: 'POST',
    body: JSON.stringify({ ai_mode: mode }),
  });
}

// ---- Preferences ----
export function fetchPreferences(prefType) {
  const params = prefType ? `?pref_type=${prefType}` : '';
  return request(`/preferences${params}`);
}
export function createPreference(prefType, prefKey, prefValue) {
  return request('/preferences', {
    method: 'POST',
    body: JSON.stringify({ pref_type: prefType, pref_key: prefKey, pref_value: prefValue }),
  });
}
export function deletePreference(id) {
  return request(`/preferences/${id}`, { method: 'DELETE' });
}

// ---- Action Items ----
export function fetchActionItems(status, emailId) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (emailId) params.set('email_id', emailId);
  const qs = params.toString();
  return request(`/actions${qs ? '?' + qs : ''}`);
}
export function extractActionItems(emailId) {
  return request(`/emails/${emailId}/extract-actions`, { method: 'POST' });
}
export function updateActionItem(id, status) {
  return request(`/actions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

// ---- Semantic Search ----
export function searchEmails(query, limit = 5) {
  return request('/search', {
    method: 'POST',
    body: JSON.stringify({ query, limit }),
  });
}

// ---- Sender Profiles ----
export function fetchSenderProfile(emailAddress) {
  return request(`/sender-profiles/${encodeURIComponent(emailAddress)}`);
}
export function updateSenderProfile(emailAddress, updates) {
  return request(`/sender-profiles/${encodeURIComponent(emailAddress)}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

// ---- Digest & Briefing ----
export function fetchDailyDigest(days = 0) {
  return request(`/digest?days=${days}`);
}
export function fetchMeetingBrief(eventId) {
  return request(`/calendar/events/${eventId}/brief`);
}
export function fetchDigestConfig() {
  return request('/digest/config');
}
export function saveDigestConfig(config) {
  return request('/digest/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  });
}
export function triggerDigestGeneration() {
  return request('/digest/generate', { method: 'POST' });
}
export function digestCardAction(emailId, actionType, data = {}) {
  return request('/digest/card-action', {
    method: 'POST',
    body: JSON.stringify({ email_id: emailId, action_type: actionType, ...data }),
  });
}
