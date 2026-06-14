import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import AppNav from './components/AppNav';
import Dashboard from './pages/Dashboard';
import InboxPage from './pages/InboxPage';
import CalendarPage from './pages/CalendarPage';
import SettingsPage from './pages/SettingsPage';
import OutlookPage from './pages/OutlookPage';
import AuthPage from './pages/AuthPage';
import './App.css';

function App() {
  const { token, authStatus } = useAuth();

  // Still loading auth status from server
  if (authStatus === null) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'var(--bg-primary)',
        flexDirection: 'column',
        gap: '16px',
      }}>
        <div style={{
          width: '40px',
          height: '40px',
          border: '3px solid var(--border)',
          borderTopColor: 'var(--accent)',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }} />
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading…</p>
      </div>
    );
  }

  // Not authenticated → show auth page
  if (!token || !authStatus?.authenticated) {
    return <AuthPage />;
  }

  // Authenticated → show app
  return (
    <div className="app-shell">
      <AppNav />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/outlook" element={<OutlookPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
