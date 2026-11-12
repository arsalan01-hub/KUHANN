import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { Listing, Page } from '../api/types';
import { ListingTable } from '../components/ListingTable';
import { Card, ErrorBox, Loading, Pagination, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';

export default function SavedTrucks({ kind }: { kind: 'saved' | 'favorite' }) {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useApi<Page<Listing>>(
    () => api.get<Page<Listing>>('/saved', { kind, page, page_size: 25 }),
    [kind, page],
  );

  const remove = async (listing: Listing) => {
    if (!listing.saved_id) return;
    try {
      await api.delete(`/saved/${listing.saved_id}`);
      toast.push('Removed', 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not remove', 'error');
    }
  };

  const title = kind === 'favorite' ? 'Favorites' : 'Saved trucks';

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>{title}</h1>
          <p>
            {kind === 'favorite'
              ? 'Shortlisted trucks you marked as favorites. Personal to your account.'
              : 'Trucks you saved for follow-up. Deleting here never touches the original advertisement.'}
          </p>
        </div>
        <div className="head-actions">
          <Link className="btn" to="/search">
            Find more trucks
          </Link>
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}

      <Card title={data ? `${data.total} record(s)` : title}>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <ListingTable items={data?.items ?? []} onSave={remove} showRisk />
            {data && (
              <Pagination
                page={data.page}
                pages={data.pages}
                total={data.total}
                pageSize={data.page_size}
                onPage={setPage}
              />
            )}
          </>
        )}
      </Card>
    </>
  );
}
