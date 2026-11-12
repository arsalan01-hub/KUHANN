import { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Page, Role, User } from '../api/types';
import { Badge, Card, DataTable, ErrorBox, Field, Loading, Modal, Pagination, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, relative } from '../lib/format';
import { useAuth } from '../context/AuthContext';

export default function Users() {
  const toast = useToast();
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState({ email: '', full_name: '', password: '', roles: ['employee'] as string[] });

  const list = useApi<Page<User>>(() => api.get<Page<User>>('/users', { page, page_size: 25, q }), [page, q]);
  const roles = useApi<{ items: Role[] }>(() => api.get('/roles'), []);

  const openCreate = () => {
    setEditing(null);
    setForm({ email: '', full_name: '', password: '', roles: ['employee'] });
    setModalOpen(true);
  };

  const openEdit = (user: User) => {
    setEditing(user);
    setForm({
      email: user.email,
      full_name: user.full_name,
      password: '',
      roles: user.roles.map((role) => role.name),
    });
    setModalOpen(true);
  };

  const save = async () => {
    try {
      if (editing) {
        await api.patch(`/users/${editing.id}`, {
          full_name: form.full_name,
          roles: form.roles,
          password: form.password || undefined,
        });
        toast.push('User updated', 'success');
      } else {
        await api.post('/users', {
          email: form.email,
          full_name: form.full_name,
          password: form.password,
          roles: form.roles,
        });
        toast.push('User created', 'success');
      }
      setModalOpen(false);
      list.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save user', 'error');
    }
  };

  const toggleActive = async (user: User) => {
    try {
      await api.patch(`/users/${user.id}`, { is_active: !user.is_active });
      toast.push(user.is_active ? 'User deactivated' : 'User re-activated', 'success');
      list.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Action failed', 'error');
    }
  };

  const unlock = async (user: User) => {
    try {
      await api.post(`/users/${user.id}/unlock`);
      toast.push('Account unlocked', 'success');
      list.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Action failed', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>User management</h1>
          <p>
            Accounts are created by administrators. There is no public registration. Five failed sign-ins
            lock an account for 15 minutes.
          </p>
        </div>
        {can('users:write') && (
          <div className="head-actions">
            <button type="button" className="btn primary" onClick={openCreate}>
              New user
            </button>
          </div>
        )}
      </div>

      <Card title="Filter">
        <Field label="Search by email or name">
          <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="name@company.com" />
        </Field>
      </Card>

      {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}

      <Card title={list.data ? `${list.data.total} user(s)` : 'Users'}>
        {list.loading && !list.data ? (
          <Loading />
        ) : (
          <>
            <DataTable
              rows={list.data?.items ?? []}
              getKey={(row) => row.id}
              columns={[
                {
                  key: 'user',
                  header: 'User',
                  render: (row) => (
                    <div>
                      <div className="row-title">{row.full_name || row.email}</div>
                      <div className="row-sub">{row.email}</div>
                    </div>
                  ),
                },
                {
                  key: 'roles',
                  header: 'Roles',
                  render: (row) => (
                    <div className="chip-row">
                      {row.roles.map((role) => (
                        <Badge key={role.id} variant="info">{role.name.replace(/_/g, ' ')}</Badge>
                      ))}
                    </div>
                  ),
                },
                {
                  key: 'state',
                  header: 'State',
                  render: (row) => (
                    <div className="stack tight" style={{ gap: 3 }}>
                      <Badge variant={row.is_active ? 'success' : 'danger'}>{row.is_active ? 'active' : 'disabled'}</Badge>
                      {row.totp_enabled && <Badge variant="info">2FA</Badge>}
                      {row.locked_until && new Date(row.locked_until) > new Date() && (
                        <Badge variant="warning">locked</Badge>
                      )}
                    </div>
                  ),
                },
                { key: 'last', header: 'Last sign-in', render: (row) => (row.last_login_at ? relative(row.last_login_at) : 'never') },
                { key: 'created', header: 'Created', render: (row) => dateTime(row.created_at) },
                {
                  key: 'actions',
                  header: 'Actions',
                  render: (row) =>
                    can('users:write') ? (
                      <div className="inline" style={{ gap: 4 }}>
                        <button type="button" className="btn sm" onClick={() => openEdit(row)}>Edit</button>
                        <button type="button" className="btn sm" onClick={() => void toggleActive(row)}>
                          {row.is_active ? 'Disable' : 'Enable'}
                        </button>
                        <button type="button" className="btn sm" onClick={() => void unlock(row)}>Unlock</button>
                      </div>
                    ) : (
                      <span className="muted small">read-only</span>
                    ),
                },
              ]}
            />
            {list.data && (
              <Pagination page={list.data.page} pages={list.data.pages} total={list.data.total} pageSize={list.data.page_size} onPage={setPage} />
            )}
          </>
        )}
      </Card>

      <Modal
        open={modalOpen}
        title={editing ? `Edit ${editing.email}` : 'Create user'}
        subtitle="Passwords must be at least 10 characters and include a letter and a digit."
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
            <button type="button" className="btn primary" onClick={() => void save()}>Save</button>
          </>
        }
      >
        {!editing && (
          <Field label="Email">
            <input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
          </Field>
        )}
        <Field label="Full name">
          <input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
        </Field>
        <Field label={editing ? 'New password (optional)' : 'Password'}>
          <input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
        </Field>
        <Field label="Roles">
          <div className="stack tight">
            {(roles.data?.items ?? []).map((role) => (
              <label key={role.id} className="checkbox">
                <input
                  type="checkbox"
                  checked={form.roles.includes(role.name)}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      roles: event.target.checked
                        ? [...form.roles, role.name]
                        : form.roles.filter((name) => name !== role.name),
                    })
                  }
                />
                {role.name.replace(/_/g, ' ')} — {role.description}
              </label>
            ))}
          </div>
        </Field>
      </Modal>
    </>
  );
}
