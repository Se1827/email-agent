import { useState, useEffect, useCallback } from 'react';
import { ChevronDown, PenSquare, Menu } from 'lucide-react';
import InboxNavbar from '../components/InboxNavbar';
import EmailList from '../components/EmailList';
import EmailDetail from '../components/EmailDetail';
import ComposeModal from '../components/ComposeModal';
import { fetchAccounts, fetchEmails, classifyAll, refreshInbox } from '../api';
import './InboxPage.css';

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
    setError(null);
    try {
      const data = await fetchEmails(selectedAccountId === 'all' ? null : selectedAccountId);
      setEmails(data);
    } catch (err) {
      setError('Cannot reach the API server. Is it running on :8000?');
    } finally {
      if (showLoading) setLoading(false);
    }
  }, [selectedAccountId]);

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
      setAccounts(data);
      if (selectedAccountId !== 'all' && !data.some((account) => account.id === selectedAccountId)) {
        setSelectedAccountId('all');
        localStorage.setItem('selectedAccountId', 'all');
      }
    }).catch(() => setAccounts([]));
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
          {selectedAccount ? selectedAccount.name.charAt(0).toUpperCase() : 'A'}
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
              <span className="account-switcher-dot" style={{ background: account.color }} />
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
