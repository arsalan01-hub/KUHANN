import { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Page } from '../api/types';
import { Badge, Card, DataTable, ErrorBox, Field, Loading, Pagination, StatusBadge, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, number, relative } from '../lib/format';

interface Provider {
  key: string;
  label: string;
  description: string;
  configured: boolean;
  status: string;
}

interface Run {
  id: string;
  provider: string;
  query: string;
  status: string;
  results_found: number;
  sources_created: number;
  duplicates_skipped: number;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  provider_configured: boolean;
  details: Record<string, unknown>;
}

interface SearchApiConfig {
  enabled: boolean;
  vendor: string;
  endpoint: string;
  cx: string;
  has_api_key: boolean;
  status: string;
}

export default function Discovery() {
  const toast = useToast();
  const [provider, setProvider] = useState('curated_directory');
  const [query, setQuery] = useState('used trucks for sale');
  const [limit, setLimit] = useState(20);
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);

  const providers = useApi<{ items: Provider[] }>(() => api.get('/discovery/providers'), []);
  const runs = useApi<Page<Run>>(() => api.get<Page<Run>>('/discovery/runs', { page, page_size: 15 }), [page]);
  const searchApi = useApi<SearchApiConfig>(() => api.get('/discovery/search-api'), []);

  const [apiForm, setApiForm] = useState({ enabled: false, vendor: 'brave', endpoint: '', cx: '', api_key: '' });
  const [apiLoaded, setApiLoaded] = useState(false);

  if (searchApi.data && !apiLoaded) {
    setApiForm({
      enabled: searchApi.data.enabled,
      vendor: searchApi.data.vendor,
      endpoint: searchApi.data.endpoint,
      cx: searchApi.data.cx,
      api_key: '',
    });
    setApiLoaded(true);
  }

  const run = async () => {
    setBusy(true);
    try {
      const result = await api.post<Run>('/discovery/run', { provider, query, limit });
      toast.push(
        result.status === 'completed'
          ? `${result.sources_created} new website(s) registered`
          : result.message,
        result.status === 'completed' ? 'success' : 'error',
      );
      runs.reload();
      providers.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Discovery failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const saveSearchApi = async () => {
    setBusy(true);
    try {
      await api.put('/discovery/search-api', {
        enabled: apiForm.enabled,
        vendor: apiForm.vendor,
        endpoint: apiForm.endpoint,
        cx: apiForm.cx,
        api_key: apiForm.api_key || undefined,
      });
      toast.push('Search API configuration saved', 'success');
      searchApi.reload();
      providers.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save configuration', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Website discovery</h1>
          <p>
            KUHHAN searches permitted discovery providers for websites that sell trucks. New domains are
            registered as candidates and inspected; nothing is collected until you approve it.
          </p>
        </div>
      </div>

      <Card title="Discovery providers" subtitle="Configured sources of new website candidates">
        {providers.loading && !providers.data ? (
          <Loading />
        ) : (
          <DataTable
            rows={providers.data?.items ?? []}
            getKey={(row) => row.key}
            columns={[
              {
                key: 'provider',
                header: 'Provider',
                render: (row) => (
                  <div>
                    <div className="row-title">{row.label}</div>
                    <div className="row-sub">{row.description}</div>
                  </div>
                ),
              },
              {
                key: 'state',
                header: 'State',
                render: (row) => <Badge variant={row.configured ? 'success' : 'warning'}>{row.configured ? 'ready' : 'needs setup'}</Badge>,
              },
              { key: 'status', header: 'Detail', render: (row) => <span className="small">{row.status}</span> },
            ]}
          />
        )}
      </Card>

      <div className="grid cols-2">
        <Card title="Run discovery" subtitle="Search the selected provider now">
          <Field label="Provider">
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {(providers.data?.items ?? []).map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}{item.configured ? '' : ' — not configured'}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Query" hint="Describe the websites you are looking for">
            <input value={query} onChange={(event) => setQuery(event.target.value)} />
          </Field>
          <Field label="Maximum results">
            <input type="number" min={1} max={100} value={limit} onChange={(event) => setLimit(Number(event.target.value))} />
          </Field>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void run()}>
            {busy ? 'Running…' : 'Start discovery'}
          </button>
        </Card>

        <Card title="External search API" subtitle="Documented search provider used for discovery">
          {searchApi.loading && !searchApi.data ? (
            <Loading />
          ) : (
            <>
              <div className={`alert ${searchApi.data?.has_api_key ? 'success' : 'warning'}`}>
                {searchApi.data?.status}
              </div>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={apiForm.enabled}
                  onChange={(event) => setApiForm({ ...apiForm, enabled: event.target.checked })}
                />
                Enable the external search API provider
              </label>
              <Field label="Vendor">
                <select value={apiForm.vendor} onChange={(event) => setApiForm({ ...apiForm, vendor: event.target.value })}>
                  <option value="brave">Brave Search</option>
                  <option value="google_cse">Google Programmable Search</option>
                  <option value="serper">Serper</option>
                  <option value="custom">Custom JSON search endpoint</option>
                </select>
              </Field>
              <Field label="Endpoint">
                <input
                  value={apiForm.endpoint}
                  onChange={(event) => setApiForm({ ...apiForm, endpoint: event.target.value })}
                  placeholder="https://api.search.brave.com/res/v1/web/search"
                />
              </Field>
              {apiForm.vendor === 'google_cse' && (
                <Field label="Search engine ID (cx)">
                  <input value={apiForm.cx} onChange={(event) => setApiForm({ ...apiForm, cx: event.target.value })} />
                </Field>
              )}
              <Field label="API key" hint="Stored encrypted. Leave blank to keep the existing key.">
                <input
                  type="password"
                  value={apiForm.api_key}
                  onChange={(event) => setApiForm({ ...apiForm, api_key: event.target.value })}
                  placeholder={searchApi.data?.has_api_key ? '•••••••• stored' : 'not configured'}
                />
              </Field>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void saveSearchApi()}>
                Save configuration
              </button>
            </>
          )}
        </Card>
      </div>

      <Card title="Discovery runs" subtitle="Every execution, including runs that could not reach a provider">
        {runs.error && <ErrorBox message={runs.error} onRetry={runs.reload} />}
        {runs.loading && !runs.data ? (
          <Loading />
        ) : (
          <>
            <DataTable
              rows={runs.data?.items ?? []}
              getKey={(row) => row.id}
              empty="No discovery runs yet"
              columns={[
                { key: 'when', header: 'Started', render: (row) => (row.started_at ? dateTime(row.started_at) : '—') },
                { key: 'provider', header: 'Provider', render: (row) => row.provider },
                { key: 'query', header: 'Query', render: (row) => row.query },
                { key: 'status', header: 'Status', render: (row) => <StatusBadge status={row.status} /> },
                { key: 'found', header: 'Found', numeric: true, render: (row) => number(row.results_found) },
                { key: 'created', header: 'New sources', numeric: true, render: (row) => number(row.sources_created) },
                { key: 'message', header: 'Detail', render: (row) => <span className="small cell-truncate">{row.message}</span> },
                { key: 'duration', header: 'Finished', render: (row) => relative(row.finished_at) },
              ]}
            />
            {runs.data && (
              <Pagination page={runs.data.page} pages={runs.data.pages} total={runs.data.total} pageSize={runs.data.page_size} onPage={setPage} />
            )}
          </>
        )}
      </Card>
    </>
  );
}
