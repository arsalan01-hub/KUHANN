import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Listing, Page } from '../api/types';
import { FilterPanel, EMPTY_FILTERS, type FilterValues } from './Filters';
import { ListingTable } from './ListingTable';
import { Card, ErrorBox, Loading, Pagination, useToast } from './ui';

export default function ListingsBrowser({
  endpoint,
  title,
  description,
  extraQuery = {},
  showRisk = true,
}: {
  endpoint: string;
  title: string;
  description: string;
  extraQuery?: Record<string, string>;
  showRisk?: boolean;
}) {
  const toast = useToast();
  const [filters, setFilters] = useState<FilterValues>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<FilterValues>(EMPTY_FILTERS);
  const [sort, setSort] = useState('newest');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<Listing> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (targetPage = 1, activeFilters = applied) => {
    setLoading(true);
    setError(null);
    try {
      const query: Record<string, string | number> = { page: targetPage, page_size: 25, sort, ...extraQuery };
      Object.entries(activeFilters).forEach(([key, value]) => {
        if (value) query[key] = value;
      });
      const response = await api.get<Page<Listing>>(endpoint, query);
      setData(response);
      setPage(targetPage);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load listings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(1, applied);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sort, endpoint]);

  const save = async (kind: 'saved' | 'favorite', listingId: string) => {
    try {
      await api.post(`/listings/${listingId}/saved`, { kind });
      toast.push(kind === 'favorite' ? 'Added to favorites' : 'Saved', 'success');
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save listing', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <div className="head-actions">
          <select value={sort} onChange={(event) => setSort(event.target.value)} style={{ width: 190 }}>
            <option value="newest">Newest discovered</option>
            <option value="oldest">Oldest discovered</option>
            <option value="price_asc">Lowest price</option>
            <option value="price_desc">Highest price</option>
            <option value="mileage_asc">Lowest mileage</option>
            <option value="mileage_desc">Highest mileage</option>
            <option value="updated">Recently checked</option>
          </select>
        </div>
      </div>

      <Card title="Filters" subtitle="Narrow the collected listings">
        <FilterPanel
          values={filters}
          onChange={setFilters}
          onSubmit={() => {
            setApplied(filters);
            void load(1, filters);
          }}
          onReset={() => {
            setFilters(EMPTY_FILTERS);
            setApplied(EMPTY_FILTERS);
            void load(1, EMPTY_FILTERS);
          }}
          busy={loading}
        />
      </Card>

      {error && <ErrorBox message={error} onRetry={() => void load(page)} />}

      <Card
        title={data ? `${data.total} listing(s)` : 'Listings'}
        subtitle={loading ? 'Loading…' : `Page ${data?.page ?? 1} of ${data?.pages ?? 1}`}
      >
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <ListingTable
              items={data?.items ?? []}
              showRisk={showRisk}
              onSave={(listing) => void save('saved', listing.id)}
              onFavorite={(listing) => void save('favorite', listing.id)}
            />
            {data && (
              <Pagination
                page={data.page}
                pages={data.pages}
                total={data.total}
                pageSize={data.page_size}
                onPage={(next) => void load(next)}
              />
            )}
          </>
        )}
      </Card>
    </>
  );
}
