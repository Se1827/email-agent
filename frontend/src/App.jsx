import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import AppNav from './components/AppNav';
import Dashboard from './pages/Dashboard';
import InboxPage from './pages/InboxPage';
import CalendarPage from './pages/CalendarPage';
import SettingsPage from './pages/SettingsPage';
import OutlookPage from './pages/OutlookPage';
import './App.css';

function App() {
  const [theme, setTheme] = useState(localStorage.getItem('app-theme') || 'default');

  useEffect(() => {
    // Apply theme class to body
    let themeClass = '';
    if (theme === 'crimson') themeClass = 'theme-crimson';
    else if (theme === 'forest') themeClass = 'theme-forest';

    document.body.className = themeClass;
    localStorage.setItem('app-theme', theme);
  }, [theme]);

  // Listen for theme changes from other components (Settings)
  useEffect(() => {
    const handleThemeChange = () => {
      setTheme(localStorage.getItem('app-theme') || 'default');
    };
    window.addEventListener('theme-changed', handleThemeChange);
    return () => window.removeEventListener('theme-changed', handleThemeChange);
  }, []);

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
