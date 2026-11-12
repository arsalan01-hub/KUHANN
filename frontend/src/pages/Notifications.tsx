import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { Notification, Page } from '../api/types';
import { Badge, Card, ErrorBox, Loading, Pagination, Tabs, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, tone } from '../lib/format';

export default function NotificationsPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const { data, loading, error, reload } = useApi<Page<Notification>>(
    () => api.get<Page<Notification>>('/notifications', { page, page_size: 25, unread_only: filter === 'unread' }),
    [page, filter],
  );

  const markRead = async (id: string) => {
    try {
      await api.post(`/notifications/${id}/read`);
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not update', 'error');
    }
  };

  const markAll = async () => {
    try {
      const result = await api.post<{ message: string }>('/notifications/read-all');
      toast.push(result.message, 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not update', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Notifications</h1>
          <p>Discovery results, saved-search matches, connector failures and operational alerts.</p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn" onClick={() => void markAll()}>
            Mark all as read
          </button>
        </div>
      </div>

      <Tabs
        tabs={[
          { key: 'all', label: 'All' },
          { key: 'unread', label: 'Unread' },
        ]}
        active={filter}
        onChange={(key) => {
          setFilter(key);
          setPage(1);
        }}
      />

      {error && <ErrorBox message={error} onRetry={reload} />}

      <Card title={data ? `${data.total} notification(s)` : 'Notifications'}>
        {loading && !data ? (
          <Loading />
        ) : (data?.items.length ?? 0) === 0 ? (
          <div className="empty">Nothing here</div>
        ) : (
          <div className="stack">
            {data?.items.map((item) => (
              <div key={item.id} className="stack tight" style={{ borderBottom: '1px solid var(--border)', paddingBottom: 10 }}>
                <div className="inline" style={{ justifyContent: 'space-between' }}>
                  <div className="inline">
                    <Badge variant={tone(item.level)}>{item.level}</Badge>
                    <strong>{item.title}</strong>
                  </div>
                  <span className="small muted">{dateTime(item.created_at)}</span>
                </div>
                {item.body && <div className="small" style={{ whiteSpace: 'pre-wrap' }}>{item.body}</div>}
                <div className="inline">
                  {item.link && (
                    <Link className="link-btn" to={item.link}>
                      Open
                    </Link>
                  )}
                  {!item.read_at && (
                    <button type="button" className="link-btn" onClick={() => void markRead(item.id)}>
                      Mark as read
                    </button>
                  )}
                  <span className="row-sub">{item.category}</span>
                </div>
              </div>
            ))}
          </div>
        )}
        {data && (
          <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
        )}
      </Card>
    </>
  );
}
