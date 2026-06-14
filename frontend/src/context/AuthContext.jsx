import { createContext, useContext, useState, useCallback, useEffect } from 'react';

const AuthContext = createContext(null);

const TOKEN_KEY = 'email_agent_token';
const DISPLAY_NAME_KEY = 'email_agent_display_name';

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || null);
  const [displayName, setDisplayName] = useState(() => sessionStorage.getItem(DISPLAY_NAME_KEY) || '');
  const [authStatus, setAuthStatus] = useState(null); // null = loading

  // On mount, check server auth status (include saved token so server can verify it)
  useEffect(() => {
    const savedToken = sessionStorage.getItem(TOKEN_KEY);
    const headers = { 'Content-Type': 'application/json' };
    if (savedToken) headers['Authorization'] = `Bearer ${savedToken}`;

    fetch('/api/auth/status', { headers })
      .then(r => r.json())
      .then(data => setAuthStatus(data))
      .catch(() => setAuthStatus({ configured: false, authenticated: false, display_name: '' }));
  }, []);

  const saveSession = useCallback((newToken, name) => {
    sessionStorage.setItem(TOKEN_KEY, newToken);
    sessionStorage.setItem(DISPLAY_NAME_KEY, name);
    setToken(newToken);
    setDisplayName(name);
  }, []);

  const login = useCallback(async (password) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Login failed');
    saveSession(data.token, data.display_name);
    setAuthStatus({ configured: true, authenticated: true, display_name: data.display_name });
    return data;
  }, [saveSession]);

  const register = useCallback(async (displayName, password) => {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Registration failed');
    saveSession(data.token, data.display_name);
    setAuthStatus({ configured: true, authenticated: true, display_name: data.display_name });
    return data;
  }, [saveSession]);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(DISPLAY_NAME_KEY);
    setToken(null);
    setDisplayName('');
    setAuthStatus(prev => prev ? { ...prev, authenticated: false } : prev);
  }, []);

  return (
    <AuthContext.Provider value={{ token, displayName, authStatus, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
