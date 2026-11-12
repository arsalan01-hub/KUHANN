import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { WebsiteSource } from '../api/types';
import { Badge, Card, ErrorBox, Field, Loading, StatusBadge, useToast } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, number, relative, titleCase } from '../lib/format';

interface ConnectorMeta {
  key: string;
  label: string;
  required_config: string[];
}

export default function SourceDetail() {
  const { sourceId } = useParams();
  const toast = useToast();
  const navigate = useNavigate();
  const { data, loading, error, reload } = useApi<WebsiteSource & { connector_catalogue: ConnectorMeta[] }>(
    () => api.get(`/sources/${sourceId}`),
    [sourceId],
  );
  const [configText, setConfigText] = useState('{}');
  const [connectorKey, setConnectorKey] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string; sample?: unknown } | null>(null);

  useEffect(() => {
    if (data) {
      setConfigText(JSON.stringify(data.connector_config ?? {}, null, 2));
      setConnectorKey(data.connector_key ?? '');
      setStatus(data.status);
    }
  }, [data]);

  const save = async () => {
    setBusy(true);
    try {
      let parsed: Record<string, unknown> = {};
      if (configText.trim()) {
        try {
          parsed = JSON.parse(configText);
        } catch {
          throw new Error('Connector configuration must be valid JSON');
        }
      }
      await api.patch(`/sources/${sourceId}`, {
        status,
        connector_key: connectorKey || null,
        connector_config: parsed,
      });
      toast.push('Source updated', 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof Error ? err.message : 'Could not save', 'error');
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    try {
      const result = await api.post<{ ok: boolean; message: string; sample?: unknown }>(
        `/sources/${sourceId}/test-connector`,
      );
      setTestResult(result);
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Test failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const collect = async () => {
    setBusy(true);
    try {
      const result = await api.post<{ created: number; updated: number; marked_unreachable: number }>(
        `/sources/${sourceId}/collect`,
        {},
      );
      toast.push(`Collected: ${result.created} new, ${result.updated} updated`, 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Collection failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm('Delete this source and all of its collected listings?')) return;
    try {
      await api.delete(`/sources/${sourceId}`);
      toast.push('Source deleted', 'success');
      navigate('/sources');
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not delete', 'error');
    }
  };

  if (loading) return <Loading label="Loading website analysis…" />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const compatibility = data.compatibility as Record<string, unknown>;
  const report = data.analysis_report as Record<string, unknown>;
  const evidence = data.truck_evidence as Record<string, unknown>;
  const keywordHits = (evidence.keyword_hits as string[] | undefined) ?? [];
  const listingCandidates = (evidence.listing_candidates as string[] | undefined) ?? [];

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>{data.name || data.domain}</h1>
          <p>
            {data.domain} · discovered {relative(data.discovered_at)} by {data.discovery_provider} ·{' '}
            {number(data.listing_count ?? data.listings_collected)} listing(s)
          </p>
        </div>
        <div className="head-actions">
          <a className="btn" href={data.homepage_url} target="_blank" rel="noreferrer noopener">
            Visit website ↗
          </a>
          <button type="button" className="btn" disabled={busy} onClick={() => void test()}>
            Test connector
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void collect()}>
            Collect now
          </button>
        </div>
      </div>

      <div className="grid sidebar-right">
        <div className="stack">
          <Card title="Inspection report" subtitle={`Inspected ${dateTime(data.last_checked_at)}`}>
            <dl className="kv">
              <dt>Current status</dt>
              <dd><StatusBadge status={data.status} /></dd>
              <dt>Access method</dt>
              <dd>{titleCase(data.access_method)}</dd>
              <dt>robots.txt</dt>
              <dd>
                {data.robots_url ? (
                  <a href={data.robots_url} target="_blank" rel="noreferrer noopener">
                    {data.robots_url}
                  </a>
                ) : (
                  '—'
                )}
                <div className="row-sub">{data.robots_notes || 'Not inspected'}</div>
              </dd>
              <dt>Crawl allowed</dt>
              <dd>
                {data.robots_allows_crawl === true
                  ? 'Yes — robots.txt permits crawling'
                  : data.robots_allows_crawl === false
                    ? 'No — robots.txt restricts crawling'
                    : 'Unknown'}
              </dd>
              <dt>Official API</dt>
              <dd>
                {data.has_official_api ? (
                  data.api_doc_url ? (
                    <a href={data.api_doc_url} target="_blank" rel="noreferrer noopener">
                      Documentation detected ↗
                    </a>
                  ) : (
                    'Detected'
                  )
                ) : (
                  'None detected'
                )}
              </dd>
              <dt>Listing page</dt>
              <dd>
                {data.listing_url ? (
                  <a href={data.listing_url} target="_blank" rel="noreferrer noopener">
                    {data.listing_url}
                  </a>
                ) : (
                  'Not identified'
                )}
              </dd>
              <dt>Terms of use</dt>
              <dd>
                {data.terms_url ? (
                  <a href={data.terms_url} target="_blank" rel="noreferrer noopener">
                    Open terms ↗
                  </a>
                ) : (
                  'Not detected'
                )}
              </dd>
              <dt>Last collection</dt>
              <dd>
                {data.last_collected_at ? dateTime(data.last_collected_at) : 'never'}
                {data.last_run_status && <Badge variant={data.last_run_status === 'success' ? 'success' : 'danger'}>{data.last_run_status}</Badge>}
              </dd>
              {data.last_error && (
                <>
                  <dt>Last error</dt>
                  <dd className="alert error small">{data.last_error}</dd>
                </>
              )}
            </dl>
            {keywordHits.length > 0 && (
              <div>
                <div className="small muted">Truck signals found on the homepage</div>
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
                    <li key={candidate} className="cell-truncate">
                      <a href={candidate} target="_blank" rel="noreferrer noopener">{candidate}</a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card title="Connector configuration" subtitle="Declarative JSON — no code execution">
            <Field label="Connector">
              <select value={connectorKey} onChange={(event) => setConnectorKey(event.target.value)}>
                <option value="">No automated connector (manual)</option>
                {(data.connector_catalogue ?? []).map((connector) => (
                  <option key={connector.key} value={connector.key}>
                    {connector.label} (requires {connector.required_config.join(', ') || 'nothing'})
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Configuration"
              hint="Examples: json_feed → {feed_url, records_path, field_map}; html_listing → {listing_url, item_selector, fields}; api_integration → {api_id}"
            >
              <textarea rows={10} value={configText} onChange={(event) => setConfigText(event.target.value)} className="mono" />
            </Field>
            {testResult && (
              <div className={`alert ${testResult.ok ? 'success' : 'error'}`}>
                {testResult.message}
                {testResult.sample ? (
                  <pre className="mono" style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(testResult.sample, null, 2)}
                  </pre>
                ) : null}
              </div>
            )}
            <div className="inline">
              <Field label="Status">
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  {[
                    'newly_discovered',
                    'under_investigation',
                    'needs_review',
                    'approved',
                    'active',
                    'manual_access_only',
                    'restricted',
                    'unsupported',
                    'temporarily_unavailable',
                    'disabled',
                    'rejected',
                  ].map((item) => (
                    <option key={item} value={item}>
                      {titleCase(item)}
                    </option>
                  ))}
                </select>
              </Field>
              <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
                Save changes
              </button>
              <button type="button" className="btn danger" onClick={() => void remove()}>
                Delete source
              </button>
            </div>
          </Card>
        </div>

        <div className="stack">
          <Card title="Compatibility assessment">
            <div className="stack tight small">
              {Object.entries(compatibility).map(([key, value]) => (
                <div key={key} className="inline" style={{ justifyContent: 'space-between' }}>
                  <span className="muted">{titleCase(key)}</span>
                  <span>
                    {typeof value === 'boolean' ? (value ? 'yes' : 'no') : Array.isArray(value) ? value.join(', ') || '—' : String(value ?? '—')}
                  </span>
                </div>
              ))}
              {Object.keys(compatibility).length === 0 && <span className="muted">Not assessed yet — run an inspection.</span>}
            </div>
          </Card>

          <Card title="Raw inspection evidence">
            <details>
              <summary className="small muted">Show report JSON</summary>
              <pre className="mono" style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>
                {JSON.stringify(report, null, 2)}
              </pre>
            </details>
          </Card>

          <Card title="Linked API integrations" actions={<Link className="btn sm" to="/api-management">API management</Link>}>
            <p className="small muted">
              To collect through an official API, create the integration under API Management, link it to
              this source, then select the <code>api_integration</code> connector with{' '}
              <code>{`{"api_id": "…"}`}</code>.
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
