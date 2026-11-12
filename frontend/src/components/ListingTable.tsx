import { Link } from 'react-router-dom';
import type { Listing } from '../api/types';
import { Badge, DataTable, Empty, StatusBadge } from './ui';
import { date, money, number, titleCase, tone } from '../lib/format';

export function ListingTable({
  items,
  onSave,
  onFavorite,
  empty = 'No trucks match these criteria',
  showRisk = false,
}: {
  items: Listing[];
  onSave?: (listing: Listing) => void;
  onFavorite?: (listing: Listing) => void;
  empty?: string;
  showRisk?: boolean;
}) {
  if (!items.length) return <Empty title={empty} hint="Adjust the filters or run a collection job to refresh sources." />;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th style={{ width: 60 }}>Photo</th>
            <th>Truck</th>
            <th className="numeric">Price</th>
            <th className="numeric">Mileage</th>
            <th className="numeric">Power</th>
            <th>Spec</th>
            <th>Location</th>
            <th>Source</th>
            <th>Quality</th>
            <th>Discovered</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((listing) => (
            <tr key={listing.id}>
              <td>
                {listing.primary_image_url ? (
                  <img className="thumb" src={listing.primary_image_url} alt="" loading="lazy" />
                ) : (
                  <div className="thumb" />
                )}
              </td>
              <td>
                <Link className="row-title" to={`/listings/${listing.id}`}>
                  {listing.manufacturer || 'Unknown'} {listing.model || ''}
                </Link>
                <div className="row-sub">
                  {listing.year ?? 'Year n/a'}
                  {listing.axle_config ? ` · ${listing.axle_config}` : ''}
                  {listing.condition ? ` · ${titleCase(listing.condition)}` : ''}
                </div>
              </td>
              <td className="numeric">
                <div className="row-title">{money(listing.price, listing.currency)}</div>
                {listing.currency !== 'EUR' && listing.price_eur ? (
                  <div className="row-sub">≈ {money(listing.price_eur)}</div>
                ) : null}
              </td>
              <td className="numeric">{listing.mileage_km ? `${number(listing.mileage_km)} km` : '—'}</td>
              <td className="numeric">{listing.power_hp ? `${number(listing.power_hp)} hp` : '—'}</td>
              <td className="small">
                {[listing.euro_class, listing.transmission, listing.fuel_type].filter(Boolean).join(' · ') || '—'}
              </td>
              <td className="small">{[listing.city, listing.country].filter(Boolean).join(', ') || '—'}</td>
              <td className="small">
                <div>{listing.source_name}</div>
                <a href={listing.original_url} target="_blank" rel="noreferrer noopener" className="row-sub">
                  Original listing ↗
                </a>
              </td>
              <td>
                <div className="stack tight" style={{ gap: 4 }}>
                  <Badge variant={listing.completeness_pct >= 80 ? 'success' : listing.completeness_pct >= 40 ? 'warning' : 'danger'}>
                    {listing.completeness_pct}% complete
                  </Badge>
                  {showRisk && listing.risk_score > 0 && (
                    <Badge variant={listing.risk_score >= 60 ? 'danger' : tone('needs_review')}>
                      risk {listing.risk_score}
                    </Badge>
                  )}
                  {listing.listing_status !== 'active' && <StatusBadge status={listing.listing_status} />}
                </div>
              </td>
              <td className="small">{date(listing.first_discovered_at)}</td>
              <td>
                <div className="stack tight" style={{ gap: 4 }}>
                  {onSave && (
                    <button type="button" className="btn sm" onClick={() => onSave(listing)}>
                      Save
                    </button>
                  )}
                  {onFavorite && (
                    <button type="button" className="btn sm" onClick={() => onFavorite(listing)}>
                      ★
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SourceStatusList({
  statuses,
}: {
  statuses: { source_id: string; name: string; domain: string; status: string; operational: boolean; last_error: string | null; last_collected_at: string | null }[];
}) {
  if (!statuses.length) return <Empty title="No approved sources yet" hint="Approve a website under Website Sources before searching it." />;
  return (
    <div className="stack tight">
      {statuses.map((item) => (
        <div key={item.source_id} className="inline" style={{ justifyContent: 'space-between' }}>
          <div>
            <Link className="row-title" to={`/sources/${item.source_id}`}>
              {item.name || item.domain}
            </Link>
            <div className="row-sub">{item.domain}</div>
          </div>
          <div className="right">
            <StatusBadge status={item.status} />
            <div className="row-sub">
              {item.operational ? 'Operational' : 'Not searchable'}
              {item.last_error ? ' · last error' : ''}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export const listingColumns = (items: Listing[]) => <ListingTable items={items} />;
