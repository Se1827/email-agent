import { useState, useEffect, useCallback } from 'react';
import { ChevronDown, PenSquare, Menu } from 'lucide-react';
import InboxNavbar from '../components/InboxNavbar';
import EmailList from '../components/EmailList';
import EmailDetail from '../components/EmailDetail';
import ComposeModal from '../components/ComposeModal';
import { fetchAccounts, fetchEmails, classifyAll, refreshInbox } from '../api';
import './InboxPage.css';

/* ── Outlook / Microsoft Graph helpers ─────────────────────────── */
const OUTLOOK_ACCOUNT = {
  id: 'outlook',
  name: 'Outlook',
  email: 'Outlook (Graph)',
  provider: 'graph',
  color: '#6366f1',
  is_active: true,
};

async function fetchGraphEmails() {
  const res = await fetch('/api/graph/mail/inbox?top=50', {
    headers: { 'Content-Type': 'application/json' },
  });
  let graphMessages = [];
  if (res.ok) {
    const data = await res.json();
    // Prefix IDs so they don't collide with regular emails
    graphMessages = (data.messages || []).map((m) => ({
      ...m,
      id: m.id.startsWith('outlook:') ? m.id : `outlook:${m.id}`,
      account_id: 'outlook',
      thread_id: m.thread_id ? (m.thread_id.startsWith('outlook:') ? m.thread_id : `outlook:${m.thread_id}`) : undefined,
    }));
  }

  // Fetch locally cached outlook emails (which includes composed Sent items)
  try {
    const localRes = await fetch('/api/emails?account_id=outlook', {
      headers: { 'Content-Type': 'application/json' },
    });
    if (localRes.ok) {
      const localData = await localRes.json();
      const existingIds = new Set(graphMessages.map(m => m.id));
      for (const msg of localData) {
        if (!existingIds.has(msg.id)) {
          graphMessages.push(msg);
        }
      }
    }
  } catch (e) {
    console.error('Failed to merge local outlook emails:', e);
  }

  return graphMessages;
}

function InboxPage() {
  const [emails, setEmails] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ priority: [], category: [], folder: 'all' });
  const [busyAction, setBusyAction] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [accounts, setAccounts] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState(() => localStorage.getItem('selectedAccountId') || 'all');
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);

  const selectedAccount = accounts.find((account) => account.id === selectedAccountId);

  const loadEmails = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      if (selectedAccountId === 'outlook') {
        // Outlook-only view: fetch from Graph endpoint
        const graphData = await fetchGraphEmails();
        setEmails(graphData);
      } else if (selectedAccountId === 'all') {
        // All accounts: merge regular + Outlook
        const [regularData, graphData] = await Promise.all([
          fetchEmails(null).catch(() => []),
          fetchGraphEmails().catch(() => []),
        ]);
        setEmails([...regularData, ...graphData]);
      } else {
        // Specific non-Outlook account
        const data = await fetchEmails(selectedAccountId);
        setEmails(data);
      }
      setError(null);
    } catch (err) {
      if (emails.length === 0) {
        setError('Cannot reach the API server. Is it running on :8000?');
      } else {
        console.error('API server unreachable, preserving existing session data:', err);
      }
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [selectedAccountId, emails.length]);

  useEffect(() => {
    loadEmails(true);
    
    // Auto-fetch polling every 5 seconds
    const interval = setInterval(() => {
      loadEmails(false);
    }, 5000);
    
    return () => clearInterval(interval);
  }, [loadEmails]);

  useEffect(() => {
    fetchAccounts().then((data) => {
      // Append the virtual Outlook account if it isn't already returned by the backend
      const allAccounts = data.some(a => a.id === 'outlook') ? data : [...data, OUTLOOK_ACCOUNT];
      setAccounts(allAccounts);
      if (selectedAccountId !== 'all' && selectedAccountId !== 'outlook' && !data.some((account) => account.id === selectedAccountId)) {
        setSelectedAccountId('all');
        localStorage.setItem('selectedAccountId', 'all');
      }
    }).catch(() => setAccounts([OUTLOOK_ACCOUNT]));
  }, [selectedAccountId]);

  const chooseAccount = (accountId) => {
    setSelectedAccountId(accountId);
    localStorage.setItem('selectedAccountId', accountId);
    setSelected(null);
    setAccountMenuOpen(false);
  };

  const handleRefresh = async () => {
    setBusyAction('refresh');
    try {
      await refreshInbox();
      await loadEmails();
      setSelected(null);
    } finally {
      setBusyAction(null);
    }
  };

  const handleClassifyAll = async () => {
    setBusyAction('classify-all');
    try {
      await classifyAll(selectedAccountId === 'all' ? null : selectedAccountId);
      await loadEmails();
    } finally {
      setBusyAction(null);
    }
  };

  const updateEmail = (updatedEmail) => {
    setEmails((prev) =>
      prev.map((e) => (e.id === updatedEmail.id ? updatedEmail : e))
    );
    setSelected(updatedEmail);
  };

  // Smart folders
  let folderFiltered = emails;
  if (filters.folder === 'unread') {
    folderFiltered = emails.filter(e => !e.is_read);
  } else if (filters.folder === 'starred') {
    folderFiltered = emails.filter(e => e.is_starred);
  } else if (filters.folder === 'critical') {
    folderFiltered = emails.filter(e => e.classification?.priority === 'critical' || e.classification?.priority === 'high');
  } else if (filters.folder === 'drafts') {
    folderFiltered = emails.filter(e => e.draft_reply);
  } else if (filters.folder === 'sent') {
    folderFiltered = emails.filter(e => e.is_sent);
  }

  // Search
  let searched = folderFiltered;
  if (searchQuery.trim()) {
    const q = searchQuery.toLowerCase();
    searched = folderFiltered.filter(e =>
      e.subject.toLowerCase().includes(q) ||
      e.sender.toLowerCase().includes(q) ||
      e.body.toLowerCase().includes(q)
    );
  }

  // Priority/category filters
  const filtered = searched.filter((e) => {
    const cls = e.classification;
    if (filters.priority.length > 0) {
      if (!cls || !filters.priority.includes(cls.priority)) return false;
    }
    if (filters.category.length > 0) {
      if (!cls || !filters.category.includes(cls.category)) return false;
    }
    return true;
  });

  // Sort
  const priorityOrder = { critical: 0, high: 1, normal: 2, low: 3 };
  const sorted = [...filtered].sort((a, b) => {
    const ca = a.classification;
    const cb = b.classification;
    if (ca && !cb) return -1;
    if (!ca && cb) return 1;
    if (ca && cb) {
      return (priorityOrder[ca.priority] ?? 9) - (priorityOrder[cb.priority] ?? 9);
    }
    return new Date(b.timestamp) - new Date(a.timestamp);
  });

  const accountSwitcher = (
    <div className="account-switcher">
      <button
        className="account-switcher-button"
        onClick={() => setAccountMenuOpen((open) => !open)}
        title="Switch account"
      >
        <span
          className="account-switcher-avatar"
          style={{ background: selectedAccount?.color || 'var(--gradient-accent)' }}
        >
          {selectedAccount?.provider === 'graph'
            ? <svg width="13" height="13" viewBox="0 0 23 23" fill="none"><path d="M1 1h10v10H1z" fill="#f25022"/><path d="M12 1h10v10H12z" fill="#7fba00"/><path d="M1 12h10v10H1z" fill="#00a4ef"/><path d="M12 12h10v10H12z" fill="#ffb900"/></svg>
            : selectedAccount ? selectedAccount.name.charAt(0).toUpperCase() : 'A'}
        </span>
        <ChevronDown size={13} />
      </button>
      {accountMenuOpen && (
        <div className="account-switcher-menu">
          <button
            className={`account-switcher-item ${selectedAccountId === 'all' ? 'active' : ''}`}
            onClick={() => chooseAccount('all')}
          >
            <span className="account-switcher-dot all" />
            <span>
              <strong>All accounts</strong>
              <small>{accounts.filter((a) => a.is_active).length || accounts.length} configured</small>
            </span>
          </button>
          {accounts.map((account) => (
            <button
              key={account.id}
              className={`account-switcher-item ${selectedAccountId === account.id ? 'active' : ''}`}
              onClick={() => chooseAccount(account.id)}
            >
              {account.provider === 'graph' ? (
                <span className="account-switcher-dot" style={{ background: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="10" height="10" viewBox="0 0 23 23" fill="none"><path d="M1 1h10v10H1z" fill="#f25022"/><path d="M12 1h10v10H12z" fill="#7fba00"/><path d="M1 12h10v10H1z" fill="#00a4ef"/><path d="M12 12h10v10H12z" fill="#ffb900"/></svg>
                </span>
              ) : (
                <span className="account-switcher-dot" style={{ background: account.color }} />
              )}
              <span>
                <strong>{account.name}</strong>
                <small>{account.email}</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="inbox-page" id="inbox-page">
      <InboxNavbar
        filters={filters}
        onFiltersChange={setFilters}
        onRefresh={handleRefresh}
        onClassifyAll={handleClassifyAll}
        busyAction={busyAction}
        emailCount={emails.length}
        classifiedCount={emails.filter((e) => e.classification).length}
        unreadCount={emails.filter((e) => !e.is_read).length}
        starredCount={emails.filter((e) => e.is_starred).length}
        sentCount={emails.filter((e) => e.is_sent).length}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        accountSwitcher={accountSwitcher}
      />
      <div className="inbox-content">
        {error ? (
          <div className="error-banner">{error}</div>
        ) : (
          <>
            <EmailList
              emails={sorted}
              selected={selected}
              onSelect={setSelected}
              loading={loading}
            />
            <EmailDetail
              email={selected}
              onUpdate={updateEmail}
              onReload={loadEmails}
            />
          </>
        )}
      </div>

      {/* Floating Compose Button */}
      <button
        className="compose-fab"
        onClick={() => setComposeOpen(true)}
        title="Compose new email"
      >
        <PenSquare size={20} />
      </button>

      {/* Compose Modal */}
      <ComposeModal
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        onSent={() => loadEmails()}
        accounts={accounts}
      />
    </div>
  );
}

export default InboxPage;
