import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { SavedSearch } from '../api/types';
import { Badge, Card, ErrorBox, Loading, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, relative, titleCase } from '../lib/format';

export default function SavedSearches() {
  const toast = useToast();
  const [busyId, setBusyId] = useState<string | null>(null);
  const { data, loading, error, reload } = useApi<{ items: SavedSearch[] }>(
    () => api.get('/saved-searches'),
    [],
  );

  const act = async (id: string, action: 'run' | 'delete' | 'toggle', current?: SavedSearch) => {
    setBusyId(id);
    try {
      if (action === 'run') {
        const result = await api.post<{ matches: number; name: string }>(`/saved-searches/${id}/run`);
        toast.push(`${result.matches} new match(es) for “${result.name}”`, 'success');
      } else if (action === 'delete') {
        await api.delete(`/saved-searches/${id}`);
        toast.push('Saved search deleted', 'success');
      } else if (action === 'toggle' && current) {
        await api.patch(`/saved-searches/${id}`, { is_active: !current.is_active });
      }
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Action failed', 'error');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Saved searches</h1>
          <p>
            KUHHAN evaluates these filters in the background worker and raises a notification when a new
            matching listing appears.
          </p>
        </div>
        <div className="head-actions">
          <Link className="btn primary" to="/search">
            Create from search
          </Link>
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}

      {loading && !data ? (
        <Loading />
      ) : (data?.items.length ?? 0) === 0 ? (
        <Card title="No saved searches yet">
          <p className="muted">
            Run a search, then use “Save this search” to start monitoring. Choose hourly, daily or
            weekly evaluation.
          </p>
        </Card>
      ) : (
        <div className="grid cols-2">
          {data?.items.map((search) => (
            <Card
              key={search.id}
              title={search.name}
              subtitle={`${titleCase(search.schedule)} · ${search.mode.replace(/_/g, ' ')}`}
              actions={
                <>
                  <Badge variant={search.is_active ? 'success' : 'neutral'}>
                    {search.is_active ? 'monitoring' : 'paused'}
                  </Badge>
                  <button
                    type="button"
                    className="btn sm"
                    disabled={busyId === search.id}
                    onClick={() => void act(search.id, 'run')}
                  >
                    Run now
                  </button>
                </>
              }
            >
              <div className="stack tight small">
                {Object.entries(search.filters || {})
                  .filter(([, value]) => value !== '' && value !== null)
                  .map(([key, value]) => (
                    <div key={key} className="inline" style={{ justifyContent: 'space-between' }}>
                      <span className="muted">{titleCase(key)}</span>
                      <span>{Array.isArray(value) ? value.join(', ') : String(value)}</span>
                    </div>
                  ))}
                {Object.keys(search.filters || {}).length === 0 && (
                  <span className="muted">No filters — matches every new listing.</span>
                )}
                <hr className="hr" />
                <div className="inline" style={{ justifyContent: 'space-between' }}>
                  <span className="muted">Sources</span>
                  <span>{search.source_ids.length ? `${search.source_ids.length} selected` : 'All active'}</span>
                </div>
                <div className="inline" style={{ justifyContent: 'space-between' }}>
                  <span className="muted">Last evaluated</span>
                  <span>{search.last_run_at ? relative(search.last_run_at) : 'never'}</span>
                </div>
                <div className="inline" style={{ justifyContent: 'space-between' }}>
                  <span className="muted">Matches last run</span>
                  <span>{search.last_match_count}</span>
                </div>
                <div className="inline" style={{ justifyContent: 'space-between' }}>
                  <span className="muted">Total matches</span>
                  <span>{search.total_matches}</span>
                </div>
                <div className="inline" style={{ justifyContent: 'space-between' }}>
                  <span className="muted">Notifications</span>
                  <span>{search.notify ? 'enabled' : 'disabled'}</span>
                </div>
                <div className="inline">
                  <button
                    type="button"
                    className="btn sm"
                    disabled={busyId === search.id}
                    onClick={() => void act(search.id, 'toggle', search)}
                  >
                    {search.is_active ? 'Pause' : 'Resume'}
                  </button>
                  <button
                    type="button"
                    className="btn sm danger"
                    disabled={busyId === search.id}
                    onClick={() => void act(search.id, 'delete')}
                  >
                    Delete
                  </button>
                  <span className="row-sub">created {dateTime(search.created_at)}</span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
