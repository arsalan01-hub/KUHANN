import { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { BackupRecord, Page } from '../api/types';
import { Badge, Card, DataTable, ErrorBox, Loading, Pagination, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { bytes, dateTime, relative } from '../lib/format';
import { useAuth } from '../context/AuthContext';

interface BackupResponse extends Page<BackupRecord> {
  directory: string;
  recovery_steps: string[];
}

export default function Backups() {
  const toast = useToast();
  const { can } = useAuth();
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const { data, loading, error, reload } = useApi<BackupResponse>(
    () => api.get<BackupResponse>('/backups', { page, page_size: 20 }),
    [page],
  );

  const create = async () => {
    setBusy(true);
    try {
      const record = await api.post<BackupRecord>('/backups');
      toast.push(`Backup ${record.filename} ${record.status}`, 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Backup failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const verify = async (id: string) => {
    try {
      const result = await api.post<BackupRecord & { verification: { ok: boolean; table_count: number; row_count: number } }>(`/backups/${id}/verify`);
      toast.push(`Verification: ${result.verification.ok ? 'ok' : 'failed'} (${result.verification.table_count} tables)`, result.verification.ok ? 'success' : 'error');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Verification failed', 'error');
    }
  };

  const prune = async () => {
    try {
      const result = await api.post<{ message: string }>('/backups/prune');
      toast.push(result.message, 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Prune failed', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Backup management</h1>
          <p>
            Backups are written to the configured directory, checksummed and read back for verification.
            Existing files are never overwritten.
          </p>
        </div>
        <div className="head-actions">
          {can('backups:write') && (
            <>
              <button type="button" className="btn" onClick={() => void prune()} disabled={busy}>
                Prune old backups
              </button>
              <button type="button" className="btn primary" onClick={() => void create()} disabled={busy}>
                {busy ? 'Creating…' : 'Create backup'}
              </button>
            </>
          )}
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && (
        <div className="alert info">
          Backup directory: <code>{data.directory}</code>. Uses <code>pg_dump</code> when the PostgreSQL
          client is installed; otherwise a verified logical JSON dump.
        </div>
      )}

      <Card title={data ? `${data.total} backup(s)` : 'Backups'}>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <DataTable
              rows={data?.items ?? []}
              getKey={(row) => row.id}
              empty="No backups created yet"
              columns={[
                { key: 'file', header: 'File', render: (row) => <span className="mono small">{row.filename}</span> },
                { key: 'method', header: 'Method', render: (row) => row.method },
                { key: 'status', header: 'Status', render: (row) => <Badge variant={row.status === 'verified' || row.status === 'completed' ? 'success' : 'danger'}>{row.status}</Badge> },
                { key: 'size', header: 'Size', numeric: true, render: (row) => bytes(row.size_bytes) },
                { key: 'rows', header: 'Rows', numeric: true, render: (row) => row.row_count || '—' },
                { key: 'created', header: 'Created', render: (row) => dateTime(row.created_at) },
                { key: 'verified', header: 'Verified', render: (row) => (row.verified_at ? relative(row.verified_at) : '—') },
                {
                  key: 'actions',
                  header: '',
                  render: (row) => (
                    <button type="button" className="btn sm" onClick={() => void verify(row.id)}>
                      Verify
                    </button>
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

      {data && (
        <Card title="Recovery procedure" subtitle="Follow these steps in order during a restore">
          <ol className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
            {data.recovery_steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p className="small muted">
            Full disaster-recovery runbook (VPS loss, corruption, ransomware) is in{' '}
            <code>documentation/07-backup-and-recovery.md</code>.
          </p>
        </Card>
      )}
    </>
  );
}
