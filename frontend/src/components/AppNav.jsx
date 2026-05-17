import { NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, Inbox, Calendar, Settings } from 'lucide-react';
import './AppNav.css';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/inbox', icon: Inbox, label: 'Inbox' },
  { to: '/calendar', icon: Calendar, label: 'Calendar' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

function AppNav() {
  const location = useLocation();

  return (
    <nav className="app-nav" id="app-nav">
      <div className="nav-brand">
        <div className="nav-brand-icon">
          <img src="/icon.png" alt="Email Agent Logo" style={{ width: 28, height: 28, objectFit: 'contain' }} />
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
              id={`nav-${label.toLowerCase()}`}
            >
              <div className="nav-link-indicator" />
              <Icon size={18} strokeWidth={isActive ? 2.2 : 1.8} />
              <span className="nav-link-label">{label}</span>
            </NavLink>
          );
        })}
      </div>

      <div className="nav-footer">
        <div className="nav-footer-badge">
          <span className="nav-footer-dot" />
          <span className="nav-footer-text">PII Shield Active</span>
        </div>
      </div>
    </nav>
  );
}

export default AppNav;
