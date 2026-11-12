import { useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Page } from '../api/types';
import { Card, DataTable, ErrorBox, Loading, Pagination, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, titleCase } from '../lib/format';

interface HistoryRow {
  id: string;
  mode: string;
  query_text: string;
  filters: Record<string, unknown>;
  source_ids: string[];
  result_count: number;
  duration_ms: number;
  created_at: string;
}

export default function SearchHistoryPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useApi<Page<HistoryRow>>(
    () => api.get<Page<HistoryRow>>('/search/history', { page, page_size: 30 }),
    [page],
  );

  const remove = async (id: string) => {
    try {
      await api.delete(`/search/history/${id}`);
      toast.push('Entry removed', 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not delete entry', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Search history</h1>
          <p>Every unified search executed in KUHHAN, with the filters applied and the result count.</p>
        </div>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      <Card title={data ? `${data.total} search(es)` : 'Search history'}>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <DataTable
              rows={data?.items ?? []}
              getKey={(row) => row.id}
              empty="No searches executed yet"
              columns={[
                { key: 'query', header: 'Query', render: (row) => <span className="row-title">{row.query_text || 'Filter-only search'}</span> },
                { key: 'mode', header: 'Mode', render: (row) => titleCase(row.mode) },
                {
                  key: 'filters',
                  header: 'Filters',
                  render: (row) => (
                    <span className="small">
                      {Object.entries(row.filters)
                        .filter(([, value]) => value !== '' && value !== null)
                        .map(([key, value]) => `${key}=${Array.isArray(value) ? value.join('|') : String(value)}`)
                        .join(', ') || '—'}
                    </span>
                  ),
                },
                { key: 'sources', header: 'Sources', render: (row) => (row.source_ids.length ? `${row.source_ids.length} selected` : 'All active') },
                { key: 'results', header: 'Results', numeric: true, render: (row) => row.result_count },
                { key: 'duration', header: 'Duration', numeric: true, render: (row) => `${row.duration_ms} ms` },
                { key: 'when', header: 'Executed', render: (row) => dateTime(row.created_at) },
                {
                  key: 'actions',
                  header: '',
                  render: (row) => (
                    <button type="button" className="btn sm" onClick={() => void remove(row.id)}>
                      Delete
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
    </>
  );
}
