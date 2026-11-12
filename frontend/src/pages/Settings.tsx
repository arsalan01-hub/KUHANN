import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import { Card, DataTable, ErrorBox, Loading, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime } from '../lib/format';
import { useAuth } from '../context/AuthContext';

interface SettingRow {
  key: string;
  value: unknown;
  default: unknown;
  description: string;
  updated_at: string | null;
}

interface SettingsResponse {
  items: SettingRow[];
  environment: Record<string, unknown>;
}

export default function Settings() {
  const toast = useToast();
  const { can } = useAuth();
  const { data, loading, error, reload } = useApi<SettingsResponse>(() => api.get('/settings'), []);
  const [edits, setEdits] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data) return;
    const next: Record<string, string> = {};
    data.items.forEach((item) => {
      if (typeof item.value === 'string' || typeof item.value === 'number') {
        next[item.key] = String(item.value);
      }
    });
    setEdits(next);
  }, [data]);

  const save = async (key: string) => {
    try {
      const raw = edits[key];
      const row = data?.items.find((item) => item.key === key);
      const value = row && typeof row.default === 'number' ? Number(raw) : raw;
      await api.put(`/settings/${encodeURIComponent(key)}`, { value });
      toast.push('Setting saved', 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save setting', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>System settings</h1>
          <p>Runtime configuration stored in the database. Secrets are managed separately and never appear here.</p>
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data ? <Loading /> : null}

      {data && (
        <>
          <Card title="Runtime environment" subtitle="Values provided by the server environment">
            <div className="grid cols-2 small">
              {Object.entries(data.environment).map(([key, value]) => (
                <div key={key} className="inline" style={{ justifyContent: 'space-between' }}>
                  <span className="muted">{key.replace(/_/g, ' ')}</span>
                  <span className="mono">{String(value)}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Settings" subtitle={`${data.items.length} configurable values`}>
            <DataTable
              rows={data.items}
              getKey={(row) => row.key}
              columns={[
                {
                  key: 'key',
                  header: 'Setting',
                  render: (row) => (
                    <div>
                      <div className="row-title mono">{row.key}</div>
                      <div className="row-sub">{row.description}</div>
                    </div>
                  ),
                },
                {
                  key: 'value',
                  header: 'Value',
                  render: (row) =>
                    typeof row.value === 'object' && row.value !== null ? (
                      <pre className="mono small" style={{ whiteSpace: 'pre-wrap', maxWidth: 420 }}>
                        {JSON.stringify(row.value, null, 2)}
                      </pre>
                    ) : (
                      <input
                        value={edits[row.key] ?? ''}
                        disabled={!can('settings:write')}
                        onChange={(event) => setEdits({ ...edits, [row.key]: event.target.value })}
                        style={{ maxWidth: 260 }}
                      />
                    ),
                },
                {
                  key: 'save',
                  header: '',
                  render: (row) =>
                    typeof row.value === 'object' && row.value !== null ? (
                      <span className="row-sub">edit via its dedicated page</span>
                    ) : (
                      can('settings:write') && (
                        <button type="button" className="btn sm" onClick={() => void save(row.key)}>
                          Save
                        </button>
                      )
                    ),
                },
                { key: 'updated', header: 'Updated', render: (row) => (row.updated_at ? dateTime(row.updated_at) : 'default') },
              ]}
            />
          </Card>
        </>
      )}
    </>
  );
}
