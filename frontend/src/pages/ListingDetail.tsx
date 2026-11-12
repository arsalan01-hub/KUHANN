import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import type { Listing } from '../api/types';
import { LineChart } from '../components/charts';
import { Badge, Card, ErrorBox, Loading, useToast } from '../components/ui';
import { useApi, useLocalState } from '../hooks/useApi';
import { date, dateTime, money, number, relative, titleCase, tone } from '../lib/format';

export default function ListingDetail() {
  const { listingId } = useParams();
  const toast = useToast();
  const [theme] = useLocalState<'light' | 'dark'>('kuhhan.theme', 'light');
  const { data, loading, error, reload } = useApi<Listing>(
    () => api.get<Listing>(`/listings/${listingId}`),
    [listingId],
  );

  if (loading) return <Loading label="Loading listing…" />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const save = async (kind: 'saved' | 'favorite') => {
    try {
      await api.post(`/listings/${data.id}/saved`, { kind });
      toast.push('Saved', 'success');
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not save', 'error');
    }
  };

  const markReviewed = async () => {
    try {
      await api.post(`/listings/${data.id}/review`, {});
      toast.push('Marked as reviewed', 'success');
      reload();
    } catch (err) {
      toast.push(err instanceof ApiError ? err.message : 'Could not update', 'error');
    }
  };

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>
            {data.manufacturer || 'Unknown make'} {data.model || ''} {data.year ? `· ${data.year}` : ''}
          </h1>
          <p>
            {data.source_name} · discovered {relative(data.first_discovered_at)} · last checked{' '}
            {relative(data.last_checked_at)}
          </p>
        </div>
        <div className="head-actions">
          <a className="btn" href={data.original_url} target="_blank" rel="noreferrer noopener">
            Open original listing ↗
          </a>
          <button type="button" className="btn" onClick={() => void save('saved')}>
            Save
          </button>
          <button type="button" className="btn" onClick={() => void save('favorite')}>
            ★ Favorite
          </button>
        </div>
      </div>

      <div className="grid sidebar-right">
        <div className="stack">
          <Card title="Advertisement data">
            <dl className="kv">
              <dt>Asking price</dt>
              <dd>
                {money(data.price, data.currency)}
                {data.currency !== 'EUR' && data.price_eur ? ` (≈ ${money(data.price_eur)})` : ''}
              </dd>
              <dt>Mileage</dt>
              <dd>{data.mileage_km ? `${number(data.mileage_km)} km` : '—'}</dd>
              <dt>Power</dt>
              <dd>{data.power_hp ? `${number(data.power_hp)} hp` : '—'}</dd>
              <dt>Axle configuration</dt>
              <dd>{data.axle_config ?? '—'} {data.axles_count ? `(${data.axles_count} axles)` : ''}</dd>
              <dt>Emission class</dt>
              <dd>{data.euro_class ?? '—'}</dd>
              <dt>Transmission / fuel</dt>
              <dd>{[data.transmission, data.fuel_type].filter(Boolean).join(' · ') || '—'}</dd>
              <dt>Cab / condition</dt>
              <dd>{[data.cab_type, data.condition].filter(Boolean).join(' · ') || '—'}</dd>
              <dt>Location</dt>
              <dd>{[data.city, data.country].filter(Boolean).join(', ') || '—'}</dd>
              <dt>Listing status</dt>
              <dd><Badge variant={tone(data.listing_status)}>{titleCase(data.listing_status)}</Badge></dd>
              <dt>Extraction</dt>
              <dd>{titleCase(data.extraction_status)} · {data.completeness_pct}% complete</dd>
              <dt>First discovered</dt>
              <dd>{dateTime(data.first_discovered_at)}</dd>
              <dt>Last checked</dt>
              <dd>{dateTime(data.last_checked_at)}</dd>
              {data.unavailable_since && (
                <>
                  <dt>Unavailable since</dt>
                  <dd>{dateTime(data.unavailable_since)} (not assumed sold)</dd>
                </>
              )}
              <dt>Original URL</dt>
              <dd>
                <a href={data.original_url} target="_blank" rel="noreferrer noopener">
                  {data.original_url}
                </a>
              </dd>
            </dl>
            {data.description && (
              <>
                <hr className="hr" />
                <div className="small" style={{ whiteSpace: 'pre-wrap' }}>{data.description}</div>
              </>
            )}
          </Card>

          <Card title="Price history" subtitle="Recorded asking prices">
            {data.price_history && data.price_history.length > 1 ? (
              <LineChart
                points={data.price_history.map((entry) => ({
                  label: date(entry.recorded_at),
                  value: Math.round(entry.price_eur ?? entry.price),
                }))}
                format={(value) => money(value)}
              />
            ) : (
              <p className="small muted">
                Only one price observation recorded so far. KUHHAN adds an entry each time a collection
                run detects a different asking price.
              </p>
            )}
          </Card>

          {data.images && data.images.length > 0 && (
            <Card title={`Images (${data.images.length})`} subtitle="Served by the original website">
              <div className="chip-row">
                {data.images.map((url) => (
                  <img key={url} src={url} alt="" className="thumb" style={{ width: 92, height: 66 }} loading="lazy" />
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="stack">
          <Card title="Data quality">
            <div className="stack tight small">
              <div className="inline" style={{ justifyContent: 'space-between' }}>
                <span>Completeness</span>
                <strong>{data.completeness_pct}%</strong>
              </div>
              <div className="progress">
                <span style={{ width: `${data.completeness_pct}%` }} />
              </div>
              {data.missing_fields.length > 0 && (
                <div>
                  <div className="muted">Missing fields</div>
                  <div className="chip-row" style={{ marginTop: 4 }}>
                    {data.missing_fields.map((field) => (
                      <Badge key={field} variant="warning">{field}</Badge>
                    ))}
                  </div>
                </div>
              )}
              {data.validation_warnings.length > 0 && (
                <div>
                  <div className="muted">Validation warnings</div>
                  <ul style={{ margin: '4px 0 0 16px' }}>
                    {data.validation_warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </Card>

          <Card title="Risk indicators" subtitle="Indicators only — not proof of fraud">
            <div className="inline" style={{ justifyContent: 'space-between' }}>
              <Badge variant={data.risk_score >= 60 ? 'danger' : data.risk_score > 0 ? 'warning' : 'success'}>
                Score {data.risk_score}
              </Badge>
              {!data.risk_reviewed && (
                <button type="button" className="btn sm" onClick={() => void markReviewed()}>
                  Mark reviewed
                </button>
              )}
            </div>
            {data.risk_reasons.length > 0 ? (
              <ul style={{ margin: '4px 0 0 16px' }} className="small">
                {data.risk_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            ) : (
              <p className="small muted">No anomalies detected for this listing.</p>
            )}
          </Card>

          <Card title="Source">
            <dl className="kv">
              <dt>Website</dt>
              <dd>
                {data.source ? (
                  <Link to={`/sources/${data.source.id}`}>{data.source.name || data.source.domain}</Link>
                ) : (
                  data.source_name
                )}
              </dd>
              <dt>Domain</dt>
              <dd>{data.source?.domain ?? '—'}</dd>
              <dt>Source status</dt>
              <dd>{data.source ? <Badge variant={tone(data.source.status)}>{titleCase(data.source.status)}</Badge> : '—'}</dd>
              {data.source?.terms_url && (
                <>
                  <dt>Website terms</dt>
                  <dd>
                    <a href={data.source.terms_url} target="_blank" rel="noreferrer noopener">
                      Open ↗
                    </a>
                  </dd>
                </>
              )}
            </dl>
          </Card>

          {data.duplicates && data.duplicates.length > 0 && (
            <Card title="Possible duplicates">
              <div className="stack tight small">
                {data.duplicates.map((duplicate) => (
                  <div key={duplicate.id}>
                    <div className="inline" style={{ justifyContent: 'space-between' }}>
                      <Link to={`/listings/${duplicate.other_listing_id}`}>Compare listing</Link>
                      <Badge variant="warning">{Math.round(duplicate.score * 100)}%</Badge>
                    </div>
                    <div className="muted">{duplicate.reasons.join(' · ')}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
      <p className="small muted">
        Theme: {theme}. KUHHAN stores a snapshot of the external advertisement. Always verify details on
        the original website before acting.
      </p>
    </>
  );
}
