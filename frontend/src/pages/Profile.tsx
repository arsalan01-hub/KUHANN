import { useState } from 'react';
import { api, ApiError } from '../api/client';
import { Badge, Card, ErrorBox, Field, Loading, useToast } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { dateTime } from '../lib/format';
import { setToken } from '../api/client';

export default function Profile() {
  const toast = useToast();
  const { user, refresh } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [secret, setSecret] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user) return <Loading />;

  const changePassword = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<{ access_token: string; message: string }>('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setToken(result.access_token);
      setCurrentPassword('');
      setNewPassword('');
      toast.push('Password changed — other sessions were signed out', 'success');
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not change password');
    } finally {
      setBusy(false);
    }
  };

  const startTotp = async () => {
    try {
      const result = await api.post<{ secret: string; otpauth_uri: string }>('/auth/2fa/setup');
      setSecret(result);
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not start 2FA setup', 'error');
    }
  };

  const enableTotp = async () => {
    try {
      await api.post('/auth/2fa/enable', { code });
      toast.push('Two-factor authentication enabled', 'success');
      setSecret(null);
      setCode('');
      await refresh();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Invalid code', 'error');
    }
  };

  const disableTotp = async () => {
    try {
      await api.post('/auth/2fa/disable', { code });
      toast.push('Two-factor authentication disabled', 'success');
      setCode('');
      await refresh();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Invalid code', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>My profile</h1>
          <p>Account details, password and two-factor authentication.</p>
        </div>
      </div>

      {error && <ErrorBox message={error} />}

      <div className="grid cols-2">
        <Card title="Account">
          <dl className="kv">
            <dt>Email</dt>
            <dd>{user.email}</dd>
            <dt>Name</dt>
            <dd>{user.full_name || '—'}</dd>
            <dt>Roles</dt>
            <dd className="chip-row">
              {user.roles.map((role) => (
                <Badge key={role.id} variant="info">{role.name.replace(/_/g, ' ')}</Badge>
              ))}
            </dd>
            <dt>Permissions</dt>
            <dd className="small">{user.permission_codes.filter((code) => code !== '*').length > 0 ? user.permission_codes.join(', ') : 'all permissions'}</dd>
            <dt>Last sign-in</dt>
            <dd>{dateTime(user.last_login_at)}</dd>
            <dt>Two-factor</dt>
            <dd>{user.totp_enabled ? <Badge variant="success">enabled</Badge> : <Badge variant="warning">not enabled</Badge>}</dd>
          </dl>
        </Card>

        <Card title="Change password" subtitle="All other sessions are signed out after a change">
          <Field label="Current password">
            <input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
          </Field>
          <Field label="New password" hint="At least 10 characters, with a letter and a digit">
            <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
          </Field>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void changePassword()}>
            Update password
          </button>
        </Card>
      </div>

      <Card title="Two-factor authentication" subtitle="TOTP compatible with any authenticator app">
        {!user.totp_enabled ? (
          <>
            {!secret ? (
              <button type="button" className="btn" onClick={() => void startTotp()}>
                Start setup
              </button>
            ) : (
              <div className="stack">
                <p className="small">
                  Add this secret to your authenticator app, then confirm a generated code.
                </p>
                <code className="mono">{secret.secret}</code>
                <code className="mono small" style={{ wordBreak: 'break-all' }}>{secret.otpauth_uri}</code>
                <Field label="Authenticator code">
                  <input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" />
                </Field>
                <button type="button" className="btn primary" onClick={() => void enableTotp()}>
                  Enable two-factor authentication
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="stack">
            <p className="small">Enter a current code to disable two-factor authentication.</p>
            <Field label="Authenticator code">
              <input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" />
            </Field>
            <button type="button" className="btn danger" onClick={() => void disableTotp()}>
              Disable 2FA
            </button>
          </div>
        )}
      </Card>
    </>
  );
}
