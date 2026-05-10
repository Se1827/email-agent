import { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import EmailList from './components/EmailList';
import EmailDetail from './components/EmailDetail';
import { fetchEmails, classifyAll, refreshInbox } from './api';
import './App.css';

function App() {
  const [emails, setEmails] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ priority: [], category: [] });
  const [busyAction, setBusyAction] = useState(null);

  const loadEmails = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchEmails();
      setEmails(data);
    } catch (err) {
      setError('Cannot reach the API server. Is it running on :8000?');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEmails();
  }, [loadEmails]);

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
      await classifyAll();
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

  // Apply filters
  const filtered = emails.filter((e) => {
    const cls = e.classification;
    if (filters.priority.length > 0) {
      if (!cls || !filters.priority.includes(cls.priority)) return false;
    }
    if (filters.category.length > 0) {
      if (!cls || !filters.category.includes(cls.category)) return false;
    }
    return true;
  });

  // Sort: classified by priority, then unclassified
  const priorityOrder = { critical: 0, high: 1, normal: 2, low: 3 };
  const sorted = [...filtered].sort((a, b) => {
    const ca = a.classification;
    const cb = b.classification;
    if (ca && !cb) return -1;
    if (!ca && cb) return 1;
    if (ca && cb) {
      return (priorityOrder[ca.priority] ?? 9) - (priorityOrder[cb.priority] ?? 9);
    }
    return 0;
  });

  return (
    <div className="app">
      <Sidebar
        filters={filters}
        onFiltersChange={setFilters}
        onRefresh={handleRefresh}
        onClassifyAll={handleClassifyAll}
        busyAction={busyAction}
        emailCount={emails.length}
        classifiedCount={emails.filter((e) => e.classification).length}
      />
      <main className="main-content">
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
      </main>
    </div>
  );
}

export default App;
