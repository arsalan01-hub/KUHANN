import { api } from '../api/client';
import { Badge, Card, DataTable, ErrorBox, Loading, Stat } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { bytes, dateTime, number, relative, titleCase } from '../lib/format';

interface HealthResponse {
  status: string;
  time: string;
  database: { ok: boolean; table_count?: number; tables?: { table: string; rows: number }[]; error?: string };
  worker: { ok: boolean; heartbeat: { last_tick?: string; pid?: number; host?: string; runs_last_tick?: number } | null };
  disk: { total_bytes: number; used_bytes: number; free_bytes: number; free_percent: number | null };
  connectors: { failing: { id: string; domain: string; last_error: string | null; consecutive_failures: number }[] };
  apis: { failing: { id: string; name: string; last_error: string | null }[] };
  jobs: { stuck: { id: string; job_type: string; started_at: string }[]; last_runs: { id: string; job_type: string; status: string; started_at: string; message: string }[] };
  backups: { count: number; last: { filename: string; status: string; created_at: string } | null };
  version: string;
}

export default function Health() {
  const { data, loading, error, reload } = useApi<HealthResponse>(() => api.get('/system/health'), []);

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>System health</h1>
          <p>Live checks of the database, background worker, disk capacity, connectors and API integrations.</p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn" onClick={reload}>
            Refresh
          </button>
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data ? (
        <Loading />
      ) : data ? (
        <>
          <div className="stat-grid">
            <Stat label="Overall status" value={<Badge variant={data.status === 'ok' ? 'success' : 'warning'}>{data.status}</Badge>} hint={`checked ${dateTime(data.time)}`} />
            <Stat label="Database" value={<Badge variant={data.database.ok ? 'success' : 'danger'}>{data.database.ok ? 'reachable' : 'error'}</Badge>} hint={`${data.database.table_count ?? 0} tables`} />
            <Stat
              label="Worker"
              value={<Badge variant={data.worker.ok ? 'success' : 'warning'}>{data.worker.ok ? 'heartbeat ok' : 'no heartbeat'}</Badge>}
              hint={data.worker.heartbeat?.last_tick ? relative(data.worker.heartbeat.last_tick) : 'worker not running'}
            />
            <Stat label="Disk free" value={bytes(data.disk.free_bytes)} hint={`${data.disk.free_percent ?? '—'}% of ${bytes(data.disk.total_bytes)}`} />
            <Stat label="Failing connectors" value={data.connectors.failing.length} />
            <Stat label="Failing APIs" value={data.apis.failing.length} />
            <Stat label="Backups" value={number(data.backups.count)} hint={data.backups.last ? `last ${relative(data.backups.last.created_at)}` : 'none yet'} />
            <Stat label="Version" value={data.version} />
          </div>

          <div className="grid cols-2">
            <Card title="Connector failures" subtitle="Sources whose last collection run failed">
              <DataTable
                rows={data.connectors.failing}
                getKey={(row) => row.id}
                empty="No connector failures"
                columns={[
                  { key: 'domain', header: 'Website', render: (row) => row.domain },
                  { key: 'failures', header: 'Consecutive', numeric: true, render: (row) => row.consecutive_failures },
                  { key: 'error', header: 'Last error', render: (row) => <span className="small cell-truncate">{row.last_error ?? '—'}</span> },
                ]}
              />
            </Card>
            <Card title="API failures" subtitle="Integrations whose last test failed">
              <DataTable
                rows={data.apis.failing}
                getKey={(row) => row.id}
                empty="No API failures"
                columns={[
                  { key: 'name', header: 'Integration', render: (row) => row.name },
                  { key: 'error', header: 'Last error', render: (row) => <span className="small cell-truncate">{row.last_error ?? '—'}</span> },
                ]}
              />
            </Card>
          </div>

          <div className="grid cols-2">
            <Card title="Database tables" subtitle="Row counts from the live database">
              <div className="scroll-y">
                <DataTable
                  rows={data.database.tables ?? []}
                  getKey={(row) => row.table}
                  columns={[
                    { key: 'table', header: 'Table', render: (row) => <span className="mono small">{row.table}</span> },
                    { key: 'rows', header: 'Rows', numeric: true, render: (row) => number(row.rows) },
                  ]}
                />
              </div>
            </Card>
            <Card title="Recent job runs">
              <DataTable
                rows={data.jobs.last_runs}
                getKey={(row) => row.id}
                empty="No job runs recorded"
                columns={[
                  { key: 'job', header: 'Job', render: (row) => titleCase(row.job_type) },
                  { key: 'status', header: 'Status', render: (row) => <Badge variant={row.status === 'success' ? 'success' : 'danger'}>{row.status}</Badge> },
                  { key: 'when', header: 'Started', render: (row) => relative(row.started_at) },
                ]}
              />
              {data.jobs.stuck.length > 0 && (
                <div className="alert warning">{data.jobs.stuck.length} job(s) have been running for more than two hours.</div>
              )}
            </Card>
          </div>
        </>
      ) : null}
    </>
  );
}
