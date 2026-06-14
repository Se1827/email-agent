import { NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, Inbox, Calendar, Settings, Mail, LogOut } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import './AppNav.css';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/inbox', icon: Inbox, label: 'Inbox' },
  { to: '/calendar', icon: Calendar, label: 'Calendar' },
  { to: '/outlook', icon: Mail, label: 'Microsoft Graph' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

function AppNav() {
  const location = useLocation();
  const { displayName, logout } = useAuth();

  return (
    <nav className="app-nav" id="app-nav">
      <div className="nav-brand">
        <div className="nav-brand-icon">
          <img src="/icon.png" alt="Email Agent Logo" style={{ width: 35, height: 35, objectFit: 'contain' }} />
        </div>
        <div className="nav-brand-text">
          <span className="nav-brand-name">Email Agent</span>
          <span className="nav-brand-tag">AI-Powered</span>
        </div>
      </div>

      <div className="nav-links">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
          const isActive = to === '/'
            ? location.pathname === '/'
            : location.pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              className={`nav-link ${isActive ? 'nav-link-active' : ''}`}
              id={`nav-${label.toLowerCase().replace(/\s+/g, '-')}`}
            >
              <div className="nav-link-indicator" />
              <Icon size={18} strokeWidth={isActive ? 2.2 : 1.8} />
              <span className="nav-link-label">{label}</span>
            </NavLink>
          );
        })}
      </div>

      <div className="nav-footer">
        {/* User identity pill */}
        {displayName && (
          <div className="nav-user">
            <div className="nav-user-avatar">{displayName[0].toUpperCase()}</div>
            <span className="nav-user-name">{displayName}</span>
            <button
              className="nav-logout-btn"
              onClick={logout}
              title="Sign out"
              id="nav-logout"
            >
              <LogOut size={14} />
            </button>
          </div>
        )}

        <div className="nav-footer-badge" style={{ marginTop: displayName ? 8 : 0 }}>
          <span className="nav-footer-dot" />
          <span className="nav-footer-text">Se1827 Submission</span>
        </div>
      </div>
    </nav>
  );
}

export default AppNav;
