import { Routes, Route, Navigate } from 'react-router-dom';
import AppNav from './components/AppNav';
import Dashboard from './pages/Dashboard';
import InboxPage from './pages/InboxPage';
import CalendarPage from './pages/CalendarPage';
import SettingsPage from './pages/SettingsPage';
import OutlookPage from './pages/OutlookPage';
import './App.css';

function App() {
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
