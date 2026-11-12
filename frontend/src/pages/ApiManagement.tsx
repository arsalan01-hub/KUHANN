import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { ApiIntegration, Mapping, Page, WebsiteSource } from '../api/types';
import { Badge, Card, DataTable, ErrorBox, Field, Loading, Modal, StatusBadge, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, number, relative, titleCase } from '../lib/format';

interface Meta {
  auth_types: string[];
  http_methods: string[];
  pagination_types: string[];
  kuhhan_fields: string[];
  transforms: string[];
}

const EMPTY_FORM = {
  name: '',
  provider_name: '',
  base_url: '',
  endpoint_path: '/',
  http_method: 'GET',
  auth_type: 'api_key',
  header_name: 'X-API-Key',
  pagination_type: 'page',
  page_parameter: 'page',
  page_size_parameter: 'limit',
  page_size: 50,
  max_pages: 5,
  records_path: '',
  response_format: 'json',
  doc_url: '',
  website_source_id: '',
  api_key: '',
  token: '',
  username: '',
  password: '',
  client_id: '',
  client_secret: '',
  token_url: '',
};

export default function ApiManagement() {
  const toast = useToast();
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [editing, setEditing] = useState<ApiIntegration | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [logsFor, setLogsFor] = useState<ApiIntegration | null>(null);

  const list = useApi<Page<ApiIntegration>>(() => api.get<Page<ApiIntegration>>('/apis', { page_size: 50 }), []);
  const meta = useApi<Meta>(() => api.get<Meta>('/apis/meta'), []);
  const sources = useApi<Page<WebsiteSource>>(
    () => api.get<Page<WebsiteSource>>('/sources', { page_size: 200 }),
    [],
  );
  const logs = useApi<Page<Record<string, unknown>>>(
    () => (logsFor ? api.get<Page<Record<string, unknown>>>(`/apis/${logsFor.id}/logs`, { page_size: 20 }) : Promise.resolve({ items: [], total: 0, page: 1, page_size: 20, pages: 0 })),
    [logsFor?.id],
  );

  useEffect(() => {
    if (!editing) return;
    setForm({
      ...EMPTY_FORM,
      name: editing.name,
      provider_name: editing.provider_name,
      base_url: editing.base_url,
      endpoint_path: editing.endpoint_path,
      http_method: editing.http_method,
      auth_type: editing.auth_type,
      header_name: editing.header_name,
      pagination_type: editing.pagination_type,
      page_parameter: editing.page_parameter,
      page_size_parameter: editing.page_size_parameter,
      page_size: editing.page_size,
      max_pages: editing.max_pages,
      records_path: editing.records_path,
      response_format: editing.response_format,
      doc_url: editing.doc_url ?? '',
      website_source_id: editing.website_source_id ?? '',
    });
    setMappings(editing.mappings ?? []);
  }, [editing]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setMappings([
      { external_field: '', kuhhan_field: 'manufacturer', transform: 'none', required: false, default_value: null },
      { external_field: '', kuhhan_field: 'model', transform: 'none', required: false, default_value: null },
      { external_field: '', kuhhan_field: 'price', transform: 'float', required: false, default_value: null },
    ]);
    setTestResult(null);
    setModalOpen(true);
  };

  const save = async () => {
    setBusy(true);
    try {
      const credentials: Record<string, string> = {};
      (['api_key', 'token', 'username', 'password', 'client_id', 'client_secret', 'token_url'] as const).forEach((key) => {
        if (form[key]) credentials[key] = form[key];
      });
      const payload: Record<string, unknown> = {
        name: form.name,
        provider_name: form.provider_name,
        base_url: form.base_url,
        endpoint_path: form.endpoint_path,
        http_method: form.http_method,
        auth_type: form.auth_type,
        header_name: form.header_name,
        pagination_type: form.pagination_type,
        page_parameter: form.page_parameter,
        page_size_parameter: form.page_size_parameter,
        page_size: Number(form.page_size),
        max_pages: Number(form.max_pages),
        records_path: form.records_path,
        response_format: form.response_format,
        doc_url: form.doc_url || null,
        website_source_id: form.website_source_id || null,
        mappings: mappings.filter((mapping) => mapping.external_field && mapping.kuhhan_field),
      };
      if (Object.keys(credentials).length) payload.credentials = credentials;
      if (editing) await api.patch(`/apis/${editing.id}`, payload);
      else await api.post('/apis', payload);
      toast.push(editing ? 'API integration updated' : 'API integration created', 'success');
      setModalOpen(false);
      list.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save the integration', 'error');
    } finally {
      setBusy(false);
    }
  };

  const act = async (integration: ApiIntegration, action: 'test' | 'activate' | 'deactivate' | 'sync' | 'delete') => {
    setBusy(true);
    try {
      if (action === 'test') {
        const result = await api.post<Record<string, unknown>>(`/apis/${integration.id}/test`);
        setTestResult(result);
        toast.push(result.ok ? 'Connection test passed' : String(result.message ?? 'Test failed'), result.ok ? 'success' : 'error');
      } else if (action === 'activate') {
        await api.post(`/apis/${integration.id}/activate`);
        toast.push('Integration activated', 'success');
      } else if (action === 'deactivate') {
        await api.post(`/apis/${integration.id}/deactivate`);
        toast.push('Integration disabled', 'success');
      } else if (action === 'sync') {
        const log = await api.post<{ status: string; records_created: number; records_updated: number; error: string | null }>(`/apis/${integration.id}/sync`, {});
        toast.push(
          log.status === 'success'
            ? `Sync finished: ${log.records_created} created, ${log.records_updated} updated`
            : `Sync failed: ${log.error}`,
          log.status === 'success' ? 'success' : 'error',
        );
      } else {
        await api.delete(`/apis/${integration.id}`);
        toast.push('Integration deleted', 'success');
      }
      list.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Action failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const credentialFields = (authType: string) => {
    if (authType === 'api_key') return ['api_key'] as const;
    if (authType === 'bearer') return ['token'] as const;
    if (authType === 'basic') return ['username', 'password'] as const;
    if (authType === 'oauth2_client_credentials') return ['client_id', 'client_secret', 'token_url'] as const;
    return [] as const;
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>API management</h1>
          <p>
            Register documented APIs, store credentials encrypted, validate the connection and mapping,
            then activate the integration. Credentials are never returned to the browser.
          </p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn primary" onClick={openCreate}>
            New integration
          </button>
        </div>
      </div>

      {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}

      {testResult && (
        <Card title="Connection test result" actions={<button type="button" className="btn sm" onClick={() => setTestResult(null)}>Dismiss</button>}>
          <div className={`alert ${testResult.ok ? 'success' : 'error'}`}>{String(testResult.message || (testResult.ok ? 'Validated' : 'Failed'))}</div>
          <pre className="mono small" style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>
            {JSON.stringify(testResult, null, 2)}
          </pre>
        </Card>
      )}

      <Card title={list.data ? `${list.data.total} integration(s)` : 'Integrations'}>
        {list.loading && !list.data ? (
          <Loading />
        ) : (
          <DataTable
            rows={list.data?.items ?? []}
            getKey={(row) => row.id}
            empty="No APIs configured yet"
            columns={[
              {
                key: 'name',
                header: 'Integration',
                render: (row) => (
                  <div>
                    <div className="row-title">{row.name}</div>
                    <div className="row-sub">
                      {row.provider_name || 'provider'} · {row.http_method} {row.base_url}
                      {row.endpoint_path}
                    </div>
                  </div>
                ),
              },
              { key: 'auth', header: 'Auth', render: (row) => <Badge variant="neutral">{titleCase(row.auth_type)}</Badge> },
              { key: 'status', header: 'Status', render: (row) => <StatusBadge status={row.status} /> },
              {
                key: 'test',
                header: 'Last test',
                render: (row) => (
                  <div>
                    <Badge variant={row.last_test_status === 'success' ? 'success' : row.last_test_status === 'failed' ? 'danger' : 'neutral'}>
                      {row.last_test_status ?? 'not tested'}
                    </Badge>
                    <div className="row-sub">{row.last_test_at ? relative(row.last_test_at) : '—'}</div>
                  </div>
                ),
              },
              { key: 'sync', header: 'Synced', numeric: true, render: (row) => number(row.records_synced) },
              { key: 'errors', header: 'Errors', numeric: true, render: (row) => number(row.errors_total) },
              {
                key: 'actions',
                header: 'Actions',
                render: (row) => (
                  <div className="inline" style={{ gap: 4 }}>
                    <button type="button" className="btn sm" disabled={busy} onClick={() => void act(row, 'test')}>Test</button>
                    {row.status === 'active' ? (
                      <button type="button" className="btn sm" disabled={busy} onClick={() => void act(row, 'deactivate')}>Disable</button>
                    ) : (
                      <button type="button" className="btn sm" disabled={busy} onClick={() => void act(row, 'activate')}>Activate</button>
                    )}
                    <button type="button" className="btn sm" disabled={busy} onClick={() => void act(row, 'sync')}>Sync</button>
                    <button type="button" className="btn sm" onClick={() => { setEditing(row); setModalOpen(true); }}>Edit</button>
                    <button type="button" className="btn sm" onClick={() => setLogsFor(row)}>Logs</button>
                    <button type="button" className="btn sm danger" disabled={busy} onClick={() => void act(row, 'delete')}>Delete</button>
                  </div>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Modal
        open={modalOpen}
        wide
        title={editing ? `Edit ${editing.name}` : 'New API integration'}
        subtitle="Only declarative field mapping is supported — arbitrary code execution is not possible."
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
            <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>Save integration</button>
          </>
        }
      >
        <div className="filter-grid">
          <Field label="Name"><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field>
          <Field label="Provider"><input value={form.provider_name} onChange={(event) => setForm({ ...form, provider_name: event.target.value })} /></Field>
          <Field label="Linked website source">
            <select value={form.website_source_id} onChange={(event) => setForm({ ...form, website_source_id: event.target.value })}>
              <option value="">Not linked</option>
              {(sources.data?.items ?? []).map((source) => (
                <option key={source.id} value={source.id}>{source.name || source.domain}</option>
              ))}
            </select>
          </Field>
          <Field label="Base URL"><input value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="https://api.example.com" /></Field>
          <Field label="Endpoint path"><input value={form.endpoint_path} onChange={(event) => setForm({ ...form, endpoint_path: event.target.value })} placeholder="/v1/trucks" /></Field>
          <Field label="HTTP method">
            <select value={form.http_method} onChange={(event) => setForm({ ...form, http_method: event.target.value })}>
              {(meta.data?.http_methods ?? ['GET', 'POST', 'PUT', 'PATCH']).map((method) => (
                <option key={method} value={method}>{method}</option>
              ))}
            </select>
          </Field>
          <Field label="Authentication">
            <select value={form.auth_type} onChange={(event) => setForm({ ...form, auth_type: event.target.value })}>
              {(meta.data?.auth_types ?? ['none', 'api_key', 'bearer', 'basic', 'oauth2_client_credentials']).map((type) => (
                <option key={type} value={type}>{titleCase(type)}</option>
              ))}
            </select>
          </Field>
          <Field label="Records path" hint="Dot path to the array, e.g. data.items"><input value={form.records_path} onChange={(event) => setForm({ ...form, records_path: event.target.value })} /></Field>
          <Field label="Pagination">
            <select value={form.pagination_type} onChange={(event) => setForm({ ...form, pagination_type: event.target.value })}>
              {(meta.data?.pagination_types ?? ['none', 'page', 'offset', 'cursor']).map((type) => (
                <option key={type} value={type}>{titleCase(type)}</option>
              ))}
            </select>
          </Field>
          <Field label="Page size"><input type="number" value={form.page_size} onChange={(event) => setForm({ ...form, page_size: Number(event.target.value) })} /></Field>
          <Field label="Max pages per sync"><input type="number" value={form.max_pages} onChange={(event) => setForm({ ...form, max_pages: Number(event.target.value) })} /></Field>
          <Field label="Documentation URL"><input value={form.doc_url} onChange={(event) => setForm({ ...form, doc_url: event.target.value })} /></Field>
        </div>

        {credentialFields(form.auth_type).length > 0 && (
          <div className="grid cols-2">
            {credentialFields(form.auth_type).map((field) => (
              <Field key={field} label={titleCase(field)} hint={editing?.credential_fields?.[field] ? `stored: ${editing.credential_fields[field]}` : 'stored encrypted'}>
                <input
                  type={field.includes('secret') || field === 'password' || field === 'api_key' || field === 'token' ? 'password' : 'text'}
                  value={form[field]}
                  onChange={(event) => setForm({ ...form, [field]: event.target.value })}
                  placeholder={editing?.has_credentials ? 'leave blank to keep' : ''}
                />
              </Field>
            ))}
          </div>
        )}

        <div className="stack tight">
          <div className="inline" style={{ justifyContent: 'space-between' }}>
            <h3>Field mapping</h3>
            <button
              type="button"
              className="btn sm"
              onClick={() => setMappings([...mappings, { external_field: '', kuhhan_field: 'manufacturer', transform: 'none', required: false, default_value: null }])}
            >
              Add mapping
            </button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>External field path</th>
                  <th>KUHHAN field</th>
                  <th>Transform</th>
                  <th>Required</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {mappings.map((mapping, index) => (
                  <tr key={index}>
                    <td>
                      <input
                        value={mapping.external_field}
                        onChange={(event) => {
                          const next = [...mappings];
                          next[index] = { ...mapping, external_field: event.target.value };
                          setMappings(next);
                        }}
                        placeholder="vehicle.price"
                      />
                    </td>
                    <td>
                      <select
                        value={mapping.kuhhan_field}
                        onChange={(event) => {
                          const next = [...mappings];
                          next[index] = { ...mapping, kuhhan_field: event.target.value };
                          setMappings(next);
                        }}
                      >
                        {(meta.data?.kuhhan_fields ?? []).map((field) => (
                          <option key={field} value={field}>{field}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <select
                        value={mapping.transform}
                        onChange={(event) => {
                          const next = [...mappings];
                          next[index] = { ...mapping, transform: event.target.value };
                          setMappings(next);
                        }}
                      >
                        {(meta.data?.transforms ?? ['none']).map((transform) => (
                          <option key={transform} value={transform}>{transform}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={mapping.required}
                        onChange={(event) => {
                          const next = [...mappings];
                          next[index] = { ...mapping, required: event.target.checked };
                          setMappings(next);
                        }}
                      />
                    </td>
                    <td>
                      <button type="button" className="btn sm" onClick={() => setMappings(mappings.filter((_, i) => i !== index))}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Modal>

      <Modal
        open={Boolean(logsFor)}
        wide
        title={`Synchronisation log — ${logsFor?.name ?? ''}`}
        onClose={() => setLogsFor(null)}
      >
        {logs.loading ? (
          <Loading />
        ) : (
          <DataTable
            rows={(logs.data?.items ?? []) as unknown as { id: string; status: string; records_fetched: number; records_created: number; records_updated: number; error: string | null; started_at: string }[]}
            getKey={(row) => row.id}
            empty="No synchronisations yet"
            columns={[
              { key: 'when', header: 'Started', render: (row) => dateTime(row.started_at) },
              { key: 'status', header: 'Status', render: (row) => <StatusBadge status={row.status} /> },
              { key: 'fetched', header: 'Fetched', numeric: true, render: (row) => row.records_fetched },
              { key: 'created', header: 'Created', numeric: true, render: (row) => row.records_created },
              { key: 'updated', header: 'Updated', numeric: true, render: (row) => row.records_updated },
              { key: 'error', header: 'Error', render: (row) => <span className="small">{row.error ?? '—'}</span> },
            ]}
          />
        )}
      </Modal>
    </>
  );
}
