import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { SearchResponse } from '../api/types';
import { FilterPanel, EMPTY_FILTERS, type FilterValues } from '../components/Filters';
import { ListingTable, SourceStatusList } from '../components/ListingTable';
import { Card, ErrorBox, Field, Loading, Modal, Pagination, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';

interface Facets {
  manufacturers: { value: string; count: number }[];
  countries: { value: string; count: number }[];
  sources: { value: string; label: string; status: string }[];
}

type Mode = 'all_active' | 'selected_sources' | 'single_source' | 'url';

export default function SearchPage() {
  const toast = useToast();
  const [filters, setFilters] = useState<FilterValues>(EMPTY_FILTERS);
  const [mode, setMode] = useState<Mode>('all_active');
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [manualUrl, setManualUrl] = useState('');
  const [sort, setSort] = useState('newest');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveSchedule, setSaveSchedule] = useState('daily');
  const [saveNotify, setSaveNotify] = useState(true);

  const facets = useApi<Facets>(() => api.get<Facets>('/search/facets'), []);
  const savedIds = useApi<Record<string, string[]>>(() => api.get('/saved/ids'), []);

  const run = async (targetPage = 1) => {
    setBusy(true);
    setError(null);
    try {
      const payload = {
        mode,
        filters: Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '')),
        source_ids: selectedSources,
        manual_url: manualUrl,
        sort,
        page: targetPage,
        page_size: 25,
      };
      const response = await api.post<SearchResponse>('/search', payload);
      setResult(response);
      setPage(targetPage);
      if (response.notes.length) response.notes.forEach((note) => toast.push(note, 'info'));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Search failed');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void run(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveListing = async (kind: 'saved' | 'favorite', listingId: string) => {
    try {
      await api.post(`/listings/${listingId}/saved`, { kind });
      toast.push(kind === 'favorite' ? 'Added to favorites' : 'Saved to your trucks', 'success');
      savedIds.reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save listing', 'error');
    }
  };

  const submitSavedSearch = async () => {
    try {
      await api.post('/saved-searches', {
        name: saveName || 'Untitled search',
        mode,
        filters: Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== '')),
        source_ids: selectedSources,
        schedule: saveSchedule,
        notify: saveNotify,
      });
      toast.push('Saved search created — monitoring runs in the background', 'success');
      setSaveOpen(false);
      setSaveName('');
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save the search', 'error');
    }
  };

  const sources = facets.data?.sources ?? [];

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Truck search</h1>
          <p>Search the KUHHAN index of collected external listings. Source website is always preserved.</p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn" onClick={() => setSaveOpen(true)}>
            Save this search
          </button>
          <button type="button" className="btn primary" onClick={() => void run(1)} disabled={busy}>
            {busy ? 'Searching…' : 'Search'}
          </button>
        </div>
      </div>

      <Card title="Search scope" subtitle="Choose which approved websites to query">
        <div className="inline">
          {(
            [
              ['all_active', 'All active websites'],
              ['selected_sources', 'Selected websites'],
              ['single_source', 'One website'],
              ['url', 'Search a website URL'],
            ] as [Mode, string][]
          ).map(([key, label]) => (
            <label key={key} className="checkbox">
              <input
                type="radio"
                name="mode"
                checked={mode === key}
                onChange={() => {
                  setMode(key);
                  if (key === 'all_active') setSelectedSources([]);
                }}
              />
              {label}
            </label>
          ))}
        </div>

        {(mode === 'selected_sources' || mode === 'single_source') && (
          <div className="stack tight">
            <div className="small muted">
              {mode === 'single_source' ? 'Select exactly one website.' : 'Select one or more approved websites.'}
            </div>
            <div className="chip-row">
              {sources
                .filter((source) => ['approved', 'active'].includes(source.status))
                .map((source) => {
                  const checked = selectedSources.includes(source.value);
                  return (
                    <label key={source.value} className="checkbox badge neutral" style={{ padding: '5px 9px' }}>
                      <input
                        type={mode === 'single_source' ? 'radio' : 'checkbox'}
                        name="source"
                        checked={checked}
                        onChange={(event) => {
                          if (mode === 'single_source') setSelectedSources([source.value]);
                          else
                            setSelectedSources((current) =>
                              event.target.checked
                                ? [...current, source.value]
                                : current.filter((id) => id !== source.value),
                            );
                        }}
                      />
                      {source.label}
                    </label>
                  );
                })}
              {sources.filter((source) => ['approved', 'active'].includes(source.status)).length === 0 && (
                <span className="small muted">
                  No approved websites yet. Approve a source first, or use “All active websites”.
                </span>
              )}
            </div>
          </div>
        )}

        {mode === 'url' && (
          <Field
            label="Website URL"
            hint="The website is inspected first. If it is new, a source record is created and must be approved before it can be searched."
          >
            <input
              value={manualUrl}
              onChange={(event) => setManualUrl(event.target.value)}
              placeholder="https://example-truck-website.com"
            />
          </Field>
        )}
      </Card>

      <Card title="Filters" subtitle="Combine as many criteria as you need">
        <FilterPanel
          values={filters}
          onChange={setFilters}
          onSubmit={() => void run(1)}
          onReset={() => {
            setFilters(EMPTY_FILTERS);
            void run(1);
          }}
          manufacturers={facets.data?.manufacturers}
          countries={facets.data?.countries}
          busy={busy}
        >
          <Field label="Sort by">
            <select value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="newest">Newest discovered</option>
              <option value="oldest">Oldest discovered</option>
              <option value="price_asc">Lowest price</option>
              <option value="price_desc">Highest price</option>
              <option value="mileage_asc">Lowest mileage</option>
              <option value="mileage_desc">Highest mileage</option>
            </select>
          </Field>
        </FilterPanel>
      </Card>

      {error && <ErrorBox message={error} onRetry={() => void run(page)} />}

      <div className="grid sidebar-right">
        <Card
          title={result ? `${result.total} result(s)` : 'Results'}
          subtitle={
            result
              ? `${result.duration_ms} ms · mode ${result.mode} · ${result.source_status.filter((s) => s.searchable).length} searchable source(s)`
              : undefined
          }
          actions={
            result && (
              <select
                value={sort}
                onChange={(event) => {
                  setSort(event.target.value);
                  void run(1);
                }}
                style={{ width: 170 }}
              >
                <option value="newest">Newest</option>
                <option value="price_asc">Price ↑</option>
                <option value="price_desc">Price ↓</option>
                <option value="mileage_asc">Mileage ↑</option>
              </select>
            )
          }
        >
          {busy && !result ? (
            <Loading label="Querying the listing index…" />
          ) : result ? (
            <>
              <ListingTable
                items={result.items}
                showRisk
                onSave={(listing) => void saveListing('saved', listing.id)}
                onFavorite={(listing) => void saveListing('favorite', listing.id)}
              />
              <Pagination
                page={result.page}
                pages={result.pages}
                total={result.total}
                pageSize={result.page_size}
                onPage={(next) => void run(next)}
              />
              <p className="small muted">{result.disclaimer}</p>
            </>
          ) : (
            <Loading label="Run a search to see results" />
          )}
        </Card>

        <div className="stack">
          <Card title="Source status" subtitle="Operational state of the sources in this search">
            {result ? <SourceStatusList statuses={result.source_status} /> : <Loading />}
          </Card>
          {result && result.notes.length > 0 && (
            <Card title="Notes">
              <div className="stack tight small">
                {result.notes.map((note, index) => (
                  <div key={index} className="alert warning">{note}</div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      <Modal
        open={saveOpen}
        title="Save this search"
        subtitle="KUHHAN runs saved searches in the background and notifies you about new matching listings."
        onClose={() => setSaveOpen(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setSaveOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn primary" onClick={() => void submitSavedSearch()}>
              Save search
            </button>
          </>
        }
      >
        <Field label="Name">
          <input value={saveName} onChange={(event) => setSaveName(event.target.value)} placeholder="Actros 1848 under 30k" />
        </Field>
        <Field label="Monitoring schedule">
          <select value={saveSchedule} onChange={(event) => setSaveSchedule(event.target.value)}>
            <option value="hourly">Hourly</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="manual">Manual only</option>
          </select>
        </Field>
        <label className="checkbox">
          <input type="checkbox" checked={saveNotify} onChange={(event) => setSaveNotify(event.target.checked)} />
          Notify me when new listings match
        </label>
        <p className="small muted">
          Filters currently applied: {Object.entries(filters).filter(([, value]) => value).map(([key, value]) => `${key}=${value}`).join(', ') || 'none'}
        </p>
      </Modal>
    </>
  );
}
