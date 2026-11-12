import { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { JobRun, JobSchedule, Page } from '../api/types';
import { Badge, Card, DataTable, ErrorBox, Field, Loading, Pagination, StatusBadge, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, relative, titleCase } from '../lib/format';

interface JobType {
  job_type: string;
  label: string;
  description: string;
}

export default function Jobs() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState('');
  const [config, setConfig] = useState('{}');
  const [busy, setBusy] = useState(false);

  const types = useApi<{ items: JobType[] }>(() => api.get('/jobs/types'), []);
  const schedules = useApi<{ items: JobSchedule[] }>(() => api.get('/jobs/schedules'), []);
  const runs = useApi<Page<JobRun>>(() => api.get<Page<JobRun>>('/jobs/runs', { page, page_size: 20 }), [page]);

  const trigger = async () => {
    setBusy(true);
    try {
      let parsed: Record<string, unknown> = {};
      try {
        parsed = config.trim() ? JSON.parse(config) : {};
      } catch {
        throw new Error('Configuration must be valid JSON');
      }
      const jobType = selected || types.data?.items[0]?.job_type;
      const result = await api.post<JobRun>('/jobs/run', { job_type: jobType, config: parsed });
      toast.push(`${titleCase(jobType ?? 'job')}: ${result.status} — ${result.message}`, result.status === 'success' ? 'success' : 'error');
      runs.reload();
      schedules.reload();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : 'Could not run job', 'error');
    } finally {
      setBusy(false);
    }
  };

  const toggleSchedule = async (schedule: JobSchedule) => {
    try {
      await api.patch(`/jobs/schedules/${schedule.id}`, { enabled: !schedule.enabled });
      schedules.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not update schedule', 'error');
    }
  };

  const updateInterval = async (schedule: JobSchedule, seconds: number) => {
    try {
      await api.patch(`/jobs/schedules/${schedule.id}`, { interval_seconds: seconds });
      toast.push('Schedule updated', 'success');
      schedules.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not update schedule', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Background jobs</h1>
          <p>
            Jobs run in the worker process, independently of any browser. Schedules execute when their
            interval elapses; manual runs execute immediately.
          </p>
        </div>
      </div>

      <div className="grid cols-2">
        <Card title="Run a job now" subtitle="Uses the same handlers as the scheduler">
          <Field label="Job type">
            <select value={selected} onChange={(event) => setSelected(event.target.value)}>
              <option value="">Select…</option>
              {(types.data?.items ?? []).map((type) => (
                <option key={type.job_type} value={type.job_type}>
                  {type.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Configuration (JSON)" hint="Example: {&quot;source_id&quot;: &quot;…&quot;} for collect_source">
            <textarea rows={4} className="mono" value={config} onChange={(event) => setConfig(event.target.value)} />
          </Field>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void trigger()}>
            {busy ? 'Running…' : 'Run job'}
          </button>
        </Card>

        <Card title="Available job types">
          <div className="stack tight">
            {(types.data?.items ?? []).map((type) => (
              <div key={type.job_type}>
                <div className="row-title">{type.label}</div>
                <div className="row-sub">{type.description}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {schedules.error && <ErrorBox message={schedules.error} onRetry={schedules.reload} />}

      <Card title="Schedules" subtitle="Change the interval or pause a scheduled job">
        {schedules.loading && !schedules.data ? (
          <Loading />
        ) : (
          <DataTable
            rows={schedules.data?.items ?? []}
            getKey={(row) => row.id}
            empty="No schedules configured"
            columns={[
              {
                key: 'name',
                header: 'Schedule',
                render: (row) => (
                  <div>
                    <div className="row-title">{row.name}</div>
                    <div className="row-sub">{row.job_type}</div>
                  </div>
                ),
              },
              {
                key: 'interval',
                header: 'Interval',
                render: (row) => (
                  <select
                    value={row.interval_seconds}
                    onChange={(event) => void updateInterval(row, Number(event.target.value))}
                    style={{ maxWidth: 170 }}
                  >
                    <option value={300}>Every 5 minutes</option>
                    <option value={3600}>Hourly</option>
                    <option value={21600}>Every 6 hours</option>
                    <option value={86400}>Daily</option>
                    <option value={604800}>Weekly</option>
                  </select>
                ),
              },
              {
                key: 'state',
                header: 'State',
                render: (row) => (
                  <button type="button" className="btn sm" onClick={() => void toggleSchedule(row)}>
                    {row.enabled ? 'Enabled' : 'Paused'}
                  </button>
                ),
              },
              { key: 'last', header: 'Last run', render: (row) => (row.last_run_at ? relative(row.last_run_at) : 'never') },
              { key: 'status', header: 'Result', render: (row) => (row.last_status ? <StatusBadge status={row.last_status} /> : '—') },
              { key: 'next', header: 'Next run', render: (row) => (row.next_run_at ? dateTime(row.next_run_at) : '—') },
            ]}
          />
        )}
      </Card>

      <Card title="Run history" subtitle="Result of every execution">
        {runs.loading && !runs.data ? (
          <Loading />
        ) : (
          <>
            <DataTable
              rows={runs.data?.items ?? []}
              getKey={(row) => row.id}
              empty="No job runs yet — is the worker running?"
              columns={[
                { key: 'when', header: 'Started', render: (row) => dateTime(row.started_at) },
                { key: 'type', header: 'Job', render: (row) => titleCase(row.job_type) },
                { key: 'status', header: 'Status', render: (row) => <StatusBadge status={row.status} /> },
                { key: 'trigger', header: 'Trigger', render: (row) => <Badge variant="neutral">{row.trigger}</Badge> },
                { key: 'duration', header: 'Duration', numeric: true, render: (row) => (row.duration_ms ? `${row.duration_ms} ms` : '—') },
                { key: 'message', header: 'Message', render: (row) => <span className="small cell-truncate">{row.message || '—'}</span> },
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
