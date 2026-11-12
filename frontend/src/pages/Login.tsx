import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Field } from '../components/ui';

export default function Login() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');
  const [totpRequired, setTotpRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await login(email, password, totp);
      if (result.totpRequired) {
        setTotpRequired(true);
        setError('Enter the 6-digit code from your authenticator app.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <aside className="login-aside">
        <div>
          <div className="brand" style={{ padding: 0 }}>
            <div className="brand-mark">K</div>
            <div>
              <div className="brand-name" style={{ color: '#fff' }}>KUHHAN</div>
              <div className="brand-sub">Truck Intelligence</div>
            </div>
          </div>
        </div>
        <div>
          <h1>One workspace for every European truck listing you track.</h1>
          <p>
            KUHHAN discovers truck-selling websites, monitors approved sources and keeps a
            structured, searchable record of external advertisements — always linking back to the
            original website.
          </p>
          <ul>
            <li>Unified search across approved sources only</li>
            <li>Autonomous website discovery with permission checks</li>
            <li>Price history, duplicates and risk indicators</li>
            <li>Saved searches with background monitoring</li>
          </ul>
        </div>
        <p style={{ fontSize: 12, color: '#93aec7' }}>
          Private professional platform. No public registration, no marketplace transactions.
        </p>
      </aside>
      <main className="login-main">
        <form className="login-card" onSubmit={submit}>
          <div>
            <h1>Sign in</h1>
            <p className="muted small">Authorised staff access only.</p>
          </div>
          {error && <div className="alert error">{error}</div>}
          <Field label="Email address" htmlFor="email">
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label="Password" htmlFor="password">
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          {totpRequired && (
            <Field label="Two-factor code" htmlFor="totp" hint="6 digits from your authenticator app">
              <input
                id="totp"
                inputMode="numeric"
                value={totp}
                onChange={(event) => setTotp(event.target.value)}
              />
            </Field>
          )}
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="login-foot">
            Accounts are created by an administrator. Five failed attempts lock an account for 15
            minutes. Sessions expire after 12 hours.
          </p>
        </form>
      </main>
    </div>
  );
}
