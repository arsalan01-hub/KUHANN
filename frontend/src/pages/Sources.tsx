import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { Page, WebsiteSource } from '../api/types';
import { Badge, Card, DataTable, ErrorBox, Field, Loading, Pagination, StatusBadge, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { date, number, relative, titleCase } from '../lib/format';

export default function Sources() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const { data, loading, error, reload } = useApi<Page<WebsiteSource>>(
    () => api.get<Page<WebsiteSource>>('/sources', { page, page_size: 25, status, q }),
    [page, status, q],
  );

  const act = async (source: WebsiteSource, action: 'approve' | 'reject' | 'collect' | 'reinspect' | 'delete' | 'disable') => {
    setBusy(source.id);
    try {
      if (action === 'approve') {
        const method = source.robots_allows_crawl === false ? 'manual_access_only' : source.access_method;
        await api.patch(`/sources/${source.id}`, {
          status: source.robots_allows_crawl === false ? 'manual_access_only' : 'approved',
          access_method: method,
        });
        toast.push(
          source.robots_allows_crawl === false
            ? 'Approved as manual-access only (robots.txt restriction)'
            : 'Source approved',
          'success',
        );
      } else if (action === 'reject') {
        await api.patch(`/sources/${source.id}`, { status: 'rejected' });
        toast.push('Source rejected', 'success');
      } else if (action === 'disable') {
        await api.patch(`/sources/${source.id}`, { status: 'disabled' });
        toast.push('Source disabled', 'success');
      } else if (action === 'reinspect') {
        await api.post(`/sources/${source.id}/reinspect`);
        toast.push('Website inspected again', 'success');
      } else if (action === 'collect') {
        const result = await api.post<{ created: number; updated: number }>(`/sources/${source.id}/collect`, {});
        toast.push(`Collection finished: ${result.created} new, ${result.updated} updated`, 'success');
      } else {
        await api.delete(`/sources/${source.id}`);
        toast.push('Source removed', 'success');
      }
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Action failed', 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Website sources</h1>
          <p>
            Every website KUHHAN knows about, its permission state and the last collection result.
            Discovery never grants collection access — approval is explicit.
          </p>
        </div>
        <div className="head-actions">
          <Link className="btn" to="/add-website">
            Add website
          </Link>
          <Link className="btn primary" to="/discovery">
            Discover websites
          </Link>
        </div>
      </div>

      <Card title="Filter">
        <div className="filter-grid">
          <Field label="Search">
            <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="domain, name or country" />
          </Field>
          <Field label="Status">
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              {[
                'newly_discovered',
                'under_investigation',
                'needs_review',
                'approved',
                'active',
                'manual_access_only',
                'restricted',
                'unsupported',
                'temporarily_unavailable',
                'disabled',
                'rejected',
              ].map((item) => (
                <option key={item} value={item}>
                  {titleCase(item)}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </Card>

      {error && <ErrorBox message={error} onRetry={reload} />}

      <Card title={data ? `${data.total} website(s)` : 'Sources'} subtitle="Sorted by newest record">
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <DataTable
              rows={data?.items ?? []}
              getKey={(row) => row.id}
              empty="No websites registered yet"
              columns={[
                {
                  key: 'site',
                  header: 'Website',
                  render: (row) => (
                    <div>
                      <Link className="row-title" to={`/sources/${row.id}`}>
                        {row.name || row.domain}
                      </Link>
                      <div className="row-sub">
                        {row.domain} · {row.country ?? '??'} · {row.category.replace(/_/g, ' ')}
                      </div>
                    </div>
                  ),
                },
                { key: 'status', header: 'Status', render: (row) => <StatusBadge status={row.status} /> },
                {
                  key: 'access',
                  header: 'Access',
                  render: (row) => (
                    <div className="stack tight" style={{ gap: 3 }}>
                      <Badge variant="neutral">{titleCase(row.access_method)}</Badge>
                      {row.has_official_api && <Badge variant="info">API found</Badge>}
                      {row.robots_allows_crawl === false && <Badge variant="warning">robots.txt blocks</Badge>}
                    </div>
                  ),
                },
                { key: 'listings', header: 'Listings', numeric: true, render: (row) => number(row.listings_collected) },
                {
                  key: 'last',
                  header: 'Last run',
                  render: (row) => (
                    <div>
                      <div>{row.last_run_status ? <Badge variant={row.last_run_status === 'success' ? 'success' : 'danger'}>{row.last_run_status}</Badge> : '—'}</div>
                      <div className="row-sub">{row.last_collected_at ? relative(row.last_collected_at) : 'never'}</div>
                    </div>
                  ),
                },
                { key: 'discovered', header: 'Discovered', render: (row) => date(row.discovered_at) },
                {
                  key: 'actions',
                  header: 'Actions',
                  render: (row) => (
                    <div className="inline" style={{ gap: 4 }}>
                      {['newly_discovered', 'under_investigation', 'needs_review'].includes(row.status) && (
                        <>
                          <button type="button" className="btn sm primary" disabled={busy === row.id} onClick={() => void act(row, 'approve')}>
                            Approve
                          </button>
                          <button type="button" className="btn sm" disabled={busy === row.id} onClick={() => void act(row, 'reject')}>
                            Reject
                          </button>
                        </>
                      )}
                      {['approved', 'active'].includes(row.status) && (
                        <button type="button" className="btn sm" disabled={busy === row.id} onClick={() => void act(row, 'collect')}>
                          Collect
                        </button>
                      )}
                      <button type="button" className="btn sm" disabled={busy === row.id} onClick={() => void act(row, 'reinspect')}>
                        Inspect
                      </button>
                      <Link className="btn sm" to={`/sources/${row.id}`}>
                        Open
                      </Link>
                    </div>
                  ),
                },
              ]}
            />
            {data && (
              <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
            )}
          </>
        )}
      </Card>
    </>
  );
}
