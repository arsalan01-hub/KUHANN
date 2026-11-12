import { useState } from 'react';
import { api } from '../api/client';
import type { AuditEntry, Page } from '../api/types';
import { Badge, Card, DataTable, ErrorBox, Field, Loading, Pagination } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime } from '../lib/format';

export default function AuditLogs() {
  const [page, setPage] = useState(1);
  const [action, setAction] = useState('');
  const [outcome, setOutcome] = useState('');
  const [entityType, setEntityType] = useState('');

  const { data, loading, error, reload } = useApi<Page<AuditEntry>>(
    () => api.get<Page<AuditEntry>>('/audit', { page, page_size: 30, action, outcome, entity_type: entityType }),
    [page, action, outcome, entityType],
  );

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Audit logs</h1>
          <p>Every privileged action, authentication attempt and configuration change is recorded here.</p>
        </div>
      </div>

      <Card title="Filter">
        <div className="filter-grid">
          <Field label="Action contains">
            <input value={action} onChange={(event) => setAction(event.target.value)} placeholder="api.test" />
          </Field>
          <Field label="Entity type">
            <input value={entityType} onChange={(event) => setEntityType(event.target.value)} placeholder="website_source" />
          </Field>
          <Field label="Outcome">
            <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              <option value="">Any</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
              <option value="blocked">Blocked</option>
            </select>
          </Field>
        </div>
      </Card>

      {error && <ErrorBox message={error} onRetry={reload} />}

      <Card title={data ? `${data.total} entries` : 'Audit trail'}>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <DataTable
              rows={data?.items ?? []}
              getKey={(row) => row.id}
              empty="No audit entries yet"
              columns={[
                { key: 'when', header: 'Time', render: (row) => dateTime(row.created_at) },
                { key: 'user', header: 'User', render: (row) => row.user_email ?? 'system' },
                { key: 'action', header: 'Action', render: (row) => <span className="mono small">{row.action}</span> },
                { key: 'entity', header: 'Entity', render: (row) => `${row.entity_type}${row.entity_id ? ` · ${row.entity_id.slice(0, 8)}…` : ''}` },
                {
                  key: 'outcome',
                  header: 'Outcome',
                  render: (row) => (
                    <Badge variant={row.outcome === 'success' ? 'success' : row.outcome === 'blocked' ? 'warning' : 'danger'}>
                      {row.outcome}
                    </Badge>
                  ),
                },
                { key: 'ip', header: 'IP', render: (row) => row.ip_address ?? '—' },
                {
                  key: 'detail',
                  header: 'Detail',
                  render: (row) => (
                    <span className="small cell-truncate" title={JSON.stringify(row.detail)}>
                      {Object.keys(row.detail ?? {}).length ? JSON.stringify(row.detail) : '—'}
                    </span>
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
