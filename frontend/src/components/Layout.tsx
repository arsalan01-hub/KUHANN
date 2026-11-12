import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useLocalState } from '../hooks/useApi';
import { relative } from '../lib/format';
import type { Notification } from '../api/types';

interface NavEntry {
  to: string;
  label: string;
  permission?: string | string[];
  section: string;
}

const NAV: NavEntry[] = [
  { to: '/', label: 'Dashboard', permission: 'dashboard:read', section: 'Overview' },
  { to: '/search', label: 'Truck Search', permission: 'search:read', section: 'Overview' },
  { to: '/listings', label: 'All Listings', permission: 'listings:read', section: 'Overview' },
  { to: '/listings/new', label: 'New Listings', permission: 'listings:read', section: 'Overview' },
  { to: '/saved', label: 'Saved Trucks', permission: 'listings:read', section: 'Overview' },
  { to: '/favorites', label: 'Favorites', permission: 'listings:read', section: 'Overview' },
  { to: '/saved-searches', label: 'Saved Searches', permission: 'search:read', section: 'Overview' },
  { to: '/price-analysis', label: 'Price Analysis', permission: 'price:read', section: 'Analysis' },
  { to: '/price-history', label: 'Price History', permission: 'price:read', section: 'Analysis' },
  { to: '/sources', label: 'Website Sources', permission: 'sources:read', section: 'Sources' },
  { to: '/discovery', label: 'Website Discovery', permission: ['sources:read', 'discovery:run'], section: 'Sources' },
  { to: '/add-website', label: 'Add Website', permission: 'sources:write', section: 'Sources' },
  { to: '/api-management', label: 'API Management', permission: 'apis:read', section: 'Sources' },
  { to: '/search-history', label: 'Search History', permission: 'search:read', section: 'Monitoring' },
  { to: '/notifications', label: 'Notifications', permission: 'notifications:read', section: 'Monitoring' },
  { to: '/jobs', label: 'Background Jobs', permission: 'jobs:read', section: 'Monitoring' },
  { to: '/health', label: 'System Health', permission: 'health:read', section: 'Monitoring' },
  { to: '/audit', label: 'Audit Logs', permission: 'audit:read', section: 'Administration' },
  { to: '/users', label: 'User Management', permission: 'users:read', section: 'Administration' },
  { to: '/roles', label: 'Roles & Permissions', permission: 'roles:read', section: 'Administration' },
  { to: '/settings', label: 'System Settings', permission: 'settings:read', section: 'Administration' },
  { to: '/backups', label: 'Backup Management', permission: 'backups:read', section: 'Administration' },
];

export default function Layout() {
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [theme, setTheme] = useLocalState<'light' | 'dark'>('kuhhan.theme', 'light');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    setSidebarOpen(false);
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await api.get<{ items: Notification[] }>('/notifications', {
          unread_only: true,
          page_size: 5,
        });
        if (!cancelled) setNotifications(response.items);
      } catch {
        /* notifications are non-critical */
      }
    };
    void load();
    const timer = window.setInterval(load, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [location.pathname]);

  const sections = Array.from(new Set(NAV.map((entry) => entry.section)));
  const initials = (user?.full_name || user?.email || 'KU').slice(0, 2).toUpperCase();
  const activeEntry = NAV.slice()
    .sort((a, b) => b.to.length - a.to.length)
    .find((entry) => location.pathname === entry.to || (entry.to !== '/' && location.pathname.startsWith(entry.to)));

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">K</div>
          <div>
            <div className="brand-name">KUHHAN</div>
            <div className="brand-sub">Truck Intelligence</div>
          </div>
        </div>
        {sections.map((section) => {
          const entries = NAV.filter((entry) => entry.section === section && (!entry.permission || can(entry.permission)));
          if (!entries.length) return null;
          return (
            <div key={section}>
              <div className="nav-section">{section}</div>
              {entries.map((entry) => (
                <NavLink
                  key={entry.to}
                  to={entry.to}
                  end={entry.to === '/' || entry.to === '/listings'}
                  className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                >
                  <span className="nav-dot" />
                  {entry.label}
                </NavLink>
              ))}
            </div>
          );
        })}
        <div className="nav-section">Account</div>
        <NavLink to="/profile" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <span className="nav-dot" />
          My Profile & 2FA
        </NavLink>
        <button
          type="button"
          className="nav-item"
          style={{ background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer', width: '100%' }}
          onClick={() => void logout().then(() => navigate('/login'))}
        >
          <span className="nav-dot" />
          Sign out
        </button>
      </aside>

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="icon-btn mobile-only"
            onClick={() => setSidebarOpen((open) => !open)}
            aria-label="Toggle navigation"
          >
            ☰
          </button>
          <div>
            <div className="topbar-title">{activeEntry?.label ?? 'KUHHAN'}</div>
          </div>
          <div className="topbar-spacer" />
          <button
            type="button"
            className="icon-btn"
            onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
            aria-label="Toggle colour theme"
            title={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
          >
            {theme === 'light' ? '◐' : '◑'}
          </button>
          <button
            type="button"
            className="icon-btn"
            style={{ position: 'relative' }}
            onClick={() => navigate('/notifications')}
            aria-label="Notifications"
            title="Notifications"
          >
            ✉
            {notifications.length > 0 && (
              <span
                className="badge danger"
                style={{ position: 'absolute', top: -6, right: -6, padding: '0 5px', fontSize: 10 }}
              >
                {notifications.length}
              </span>
            )}
          </button>
          <div style={{ position: 'relative' }}>
            <button
              type="button"
              className="user-chip"
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <span className="avatar">{initials}</span>
              <span className="user-meta">
                <strong>{user?.full_name || user?.email}</strong>
                <span>{user?.roles?.map((role) => role.name.replace(/_/g, ' ')).join(', ') || 'user'}</span>
              </span>
            </button>
            {menuOpen && (
              <div
                className="card"
                style={{ position: 'absolute', right: 0, top: 42, width: 260, zIndex: 60 }}
              >
                <div className="small muted">Signed in as</div>
                <div className="row-title">{user?.email}</div>
                {notifications.slice(0, 3).map((item) => (
                  <div key={item.id} className="small">
                    <strong>{item.title}</strong>
                    <div className="muted">{relative(item.created_at)}</div>
                  </div>
                ))}
                <hr className="hr" />
                <button type="button" className="btn sm" onClick={() => navigate('/profile')}>
                  My profile
                </button>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => void logout().then(() => navigate('/login'))}
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
