import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { WebsiteSource } from '../api/types';
import { Badge, Card, ErrorBox, Field, Loading, StatusBadge, useToast } from '../components/ui';
import { titleCase } from '../lib/format';

export default function AddWebsite() {
  const toast = useToast();
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const [category, setCategory] = useState('marketplace');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<WebsiteSource | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const source = await api.post<WebsiteSource>('/sources', { url, name: name || undefined, category });
      setResult(source);
      toast.push('Website registered and inspected', 'success');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add the website');
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    if (!result) return;
    try {
      const updated = await api.patch<WebsiteSource>(`/sources/${result.id}`, {
        status: result.robots_allows_crawl === false ? 'manual_access_only' : 'approved',
        access_method: result.robots_allows_crawl === false ? 'manual' : result.access_method,
      });
      setResult(updated);
      toast.push('Website approved', 'success');
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not approve', 'error');
    }
  };

  const compatibility = (result?.compatibility ?? {}) as Record<string, unknown>;
  const evidence = (result?.truck_evidence ?? {}) as Record<string, unknown>;
  const keywordHits = (evidence.keyword_hits as string[] | undefined) ?? [];
  const listingCandidates = (evidence.listing_candidates as string[] | undefined) ?? [];

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Add website</h1>
          <p>
            Enter a truck-selling website. KUHHAN validates the address, inspects robots.txt and the
            public page, looks for an API or listing pages, and produces an analysis report. You decide
            whether collection is permitted.
          </p>
        </div>
      </div>

      <Card title="Website address">
        <form className="stack" onSubmit={submit}>
          <div className="filter-grid">
            <Field label="Website URL" hint="Example: https://example-truck-website.com">
              <input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example-truck-website.com"
                required
              />
            </Field>
            <Field label="Display name (optional)">
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Example Trucks" />
            </Field>
            <Field label="Category">
              <select value={category} onChange={(event) => setCategory(event.target.value)}>
                {['marketplace', 'dealer', 'dealer_network', 'auction', 'classifieds', 'manufacturer'].map((item) => (
                  <option key={item} value={item}>
                    {titleCase(item)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          {error && <ErrorBox message={error} />}
          <div className="inline">
            <button type="submit" className="btn primary" disabled={busy || !url}>
              {busy ? 'Inspecting website…' : 'Analyse website'}
            </button>
            {result && (
              <Link className="btn" to={`/sources/${result.id}`}>
                Open source record
              </Link>
            )}
          </div>
        </form>
        {busy && <Loading label="Fetching robots.txt and homepage, this can take a few seconds…" />}
      </Card>

      {result && (
        <>
          <Card
            title={`Analysis: ${result.domain}`}
            subtitle={`Inspection ${
              (result.analysis_report as { http_status?: number | null })?.http_status
                ? 'completed'
                : 'did not reach the website'
            }`}
            actions={
              <>
                <StatusBadge status={result.status} />
                {['newly_discovered', 'under_investigation', 'needs_review'].includes(result.status) && (
                  <button type="button" className="btn sm primary" onClick={() => void approve()}>
                    Approve source
                  </button>
                )}
              </>
            }
          >
            <dl className="kv">
              <dt>Detected name</dt>
              <dd>{result.name}</dd>
              <dt>Country / language</dt>
              <dd>{[result.country, result.language].filter(Boolean).join(' · ') || 'unknown'}</dd>
              <dt>robots.txt</dt>
              <dd>
                {result.robots_notes || 'not available'}
                {result.robots_url && (
                  <div className="row-sub">
                    <a href={result.robots_url} target="_blank" rel="noreferrer noopener">
                      {result.robots_url}
                    </a>
                  </div>
                )}
              </dd>
              <dt>Official API</dt>
              <dd>
                {result.has_official_api ? 'Documentation detected' : 'No API documentation found'}
                {result.api_doc_url && (
                  <div className="row-sub">
                    <a href={result.api_doc_url} target="_blank" rel="noreferrer noopener">
                      {result.api_doc_url}
                    </a>
                  </div>
                )}
              </dd>
              <dt>Listing page</dt>
              <dd>
                {result.listing_url ? (
                  <a href={result.listing_url} target="_blank" rel="noreferrer noopener">
                    {result.listing_url}
                  </a>
                ) : (
                  'not identified'
                )}
              </dd>
              <dt>Terms of use</dt>
              <dd>
                {result.terms_url ? (
                  <a href={result.terms_url} target="_blank" rel="noreferrer noopener">
                    {result.terms_url}
                  </a>
                ) : (
                  'not detected'
                )}
              </dd>
              <dt>Recommended handling</dt>
              <dd>
                {titleCase(result.access_method)} · {titleCase(result.status)}
              </dd>
              {result.last_error && (
                <>
                  <dt>Error</dt>
                  <dd className="alert error small">{result.last_error}</dd>
                </>
              )}
            </dl>

            {keywordHits.length > 0 && (
              <div>
                <div className="small muted">Truck-related signals</div>
                <div className="chip-row" style={{ marginTop: 4 }}>
                  {keywordHits.map((keyword) => (
                    <Badge key={keyword} variant="info">{keyword}</Badge>
                  ))}
                </div>
              </div>
            )}
            {listingCandidates.length > 0 && (
              <div>
                <div className="small muted">Candidate listing pages</div>
                <ul className="small" style={{ margin: '4px 0 0 16px' }}>
                  {listingCandidates.map((candidate) => (
                    <li key={candidate}>
                      <a href={candidate} target="_blank" rel="noreferrer noopener">{candidate}</a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {Object.keys(compatibility).length > 0 && (
              <div className="grid cols-2 small">
                {Object.entries(compatibility).map(([key, value]) => (
                  <div key={key} className="inline" style={{ justifyContent: 'space-between' }}>
                    <span className="muted">{titleCase(key)}</span>
                    <span>
                      {typeof value === 'boolean' ? (value ? 'yes' : 'no') : Array.isArray(value) ? value.join(', ') || '—' : String(value ?? '—')}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div className="alert info">
              Finding a website does not authorise automated collection. Review the website terms and the
              robots.txt result before approving, and configure a connector under the source record.
            </div>
          </Card>
        </>
      )}
    </>
  );
}
