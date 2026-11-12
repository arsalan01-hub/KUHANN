import { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Role } from '../api/types';
import { Badge, Card, ErrorBox, Field, Loading, Modal, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { titleCase } from '../lib/format';

interface PermissionRow {
  id: string;
  code: string;
  description: string;
}

export default function Roles() {
  const toast = useToast();
  const [draft, setDraft] = useState<Record<string, string[]>>({});
  const [open, setOpen] = useState(false);
  const [newRole, setNewRole] = useState({ name: '', description: '' });
  const [busy, setBusy] = useState<string | null>(null);

  const roles = useApi<{ items: Role[] }>(() => api.get('/roles'), []);
  const permissions = useApi<{ items: PermissionRow[] }>(() => api.get('/permissions'), []);

  const codesFor = (role: Role) => draft[role.id] ?? role.permission_codes ?? [];

  const toggle = (role: Role, code: string) => {
    const current = new Set(codesFor(role));
    if (current.has(code)) current.delete(code);
    else current.add(code);
    setDraft({ ...draft, [role.id]: Array.from(current) });
  };

  const save = async (role: Role) => {
    setBusy(role.id);
    try {
      await api.patch(`/roles/${role.id}`, { permissions: codesFor(role) });
      toast.push(`Permissions updated for ${role.name}`, 'success');
      roles.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save permissions', 'error');
    } finally {
      setBusy(null);
    }
  };

  const create = async () => {
    try {
      await api.post('/roles', {
        name: newRole.name.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
        description: newRole.description,
        permissions: [],
      });
      toast.push('Role created', 'success');
      setOpen(false);
      setNewRole({ name: '', description: '' });
      roles.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not create role', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Roles &amp; permissions</h1>
          <p>
            Every permission is enforced on the backend. Super administrators hold all permissions
            implicitly; the system roles can be adjusted but not deleted.
          </p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn primary" onClick={() => setOpen(true)}>
            New role
          </button>
        </div>
      </div>

      {roles.error && <ErrorBox message={roles.error} onRetry={roles.reload} />}

      {roles.loading && !roles.data ? (
        <Loading />
      ) : (
        <div className="stack">
          {(roles.data?.items ?? []).map((role) => {
            const selected = codesFor(role);
            return (
              <Card
                key={role.id}
                title={role.name.replace(/_/g, ' ')}
                subtitle={role.description}
                actions={
                  <>
                    <Badge variant={role.is_system ? 'info' : 'neutral'}>
                      {role.is_system ? 'system role' : 'custom role'}
                    </Badge>
                    <Badge variant="neutral">{selected.length} permission(s)</Badge>
                    <button type="button" className="btn sm primary" disabled={busy === role.id} onClick={() => void save(role)}>
                      Save
                    </button>
                  </>
                }
              >
                <div className="grid cols-3">
                  {(permissions.data?.items ?? []).map((permission) => (
                    <label key={permission.id} className="checkbox" title={permission.description}>
                      <input
                        type="checkbox"
                        checked={selected.includes(permission.code)}
                        onChange={() => toggle(role, permission.code)}
                      />
                      <span className="small">{permission.code}</span>
                    </label>
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        open={open}
        title="New role"
        onClose={() => setOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button>
            <button type="button" className="btn primary" onClick={() => void create()}>Create role</button>
          </>
        }
      >
        <Field label="Name" hint="Lowercase letters, digits and underscores">
          <input value={newRole.name} onChange={(event) => setNewRole({ ...newRole, name: event.target.value })} placeholder="logistics_coordinator" />
        </Field>
        <Field label="Description">
          <input value={newRole.description} onChange={(event) => setNewRole({ ...newRole, description: event.target.value })} />
        </Field>
        <p className="small muted">Permissions can be assigned after the role is created.</p>
      </Modal>

      <Card title="Permission catalogue" subtitle="Codes referenced by the API and the interface">
        <div className="grid cols-2 small">
          {(permissions.data?.items ?? []).map((permission) => (
            <div key={permission.id}>
              <strong>{permission.code}</strong> — <span className="muted">{permission.description}</span>
            </div>
          ))}
        </div>
        <p className="small muted">Total: {permissions.data?.items.length ?? 0} permissions · {titleCase('rbac')} enforced server-side.</p>
      </Card>
    </>
  );
}
