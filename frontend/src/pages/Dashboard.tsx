import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { DashboardData } from '../api/types';
import { BarChart, LineChart, Donut } from '../components/charts';
import { Badge, Card, ErrorBox, Loading, Stat } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { dateTime, money, number, relative, titleCase, tone } from '../lib/format';

export default function Dashboard() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useApi<DashboardData>(
    () => api.get<DashboardData>('/dashboard'),
    [],
  );

  if (loading) return <Loading label="Loading operational overview…" />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;

  const totals = data.totals;
  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Operational dashboard</h1>
          <p>
            Live figures from the KUHHAN database · generated {dateTime(data.generated_at)}
          </p>
        </div>
        <div className="head-actions">
          <Link className="btn" to="/add-website">
            Add website
          </Link>
          <Link className="btn" to="/discovery">
            Run discovery
          </Link>
          <Link className="btn primary" to="/search">
            Search trucks
          </Link>
        </div>
      </div>

      <div className="stat-grid">
        <Stat label="Total listings" value={number(totals.listings_total)} hint={`${number(totals.prices_tracked)} with price`} />
        <Stat label="Active listings" value={number(totals.listings_active)} hint="Currently published externally" />
        <Stat label="New listings" value={number(totals.listings_new)} hint="Discovered in the current window" />
        <Stat label="Average asking price" value={money(totals.average_price_eur ?? null)} hint="EUR, converted from source currency" />
        <Stat label="Registered sources" value={number(totals.sources_total)} hint={`${number(totals.sources_active)} approved / active`} />
        <Stat label="Pending approvals" value={number(totals.sources_pending)} hint="Websites awaiting review" />
        <Stat label="Active APIs" value={`${number(totals.apis_active)} / ${number(totals.apis_total)}`} hint="Configured integrations" />
        <Stat label="Failed connectors" value={number(totals.connectors_failing)} hint="Last run failed" />
      </div>

      <div className="grid sidebar-right">
        <Card title="Listings discovered" subtitle="Daily count over the last 14 days">
          <LineChart
            points={data.charts.listings_by_day.map((item) => ({
              label: item.date?.slice(5) ?? '',
              value: item.count,
            }))}
            format={(value) => String(value)}
          />
        </Card>
        <Card title="Sources by status" subtitle="Approval and operational state">
          <Donut
            segments={data.charts.sources_by_status.map((item) => ({
              label: titleCase(item.status),
              value: item.count,
            }))}
          />
        </Card>
      </div>

      <div className="grid cols-2">
        <Card title="Average asking price by manufacturer" subtitle="EUR, highest-volume manufacturers">
          <BarChart
            items={data.charts.price_by_manufacturer.map((item) => ({
              label: item.manufacturer,
              value: Math.round(item.avg_price_eur),
            }))}
            format={(value) => money(value)}
          />
        </Card>
        <Card title="Listings by country" subtitle="Last known listing country">
          <BarChart
            items={data.charts.listings_by_country.map((item) => ({
              label: item.country,
              value: item.count,
            }))}
          />
        </Card>
      </div>

      <div className="grid cols-2">
        <Card
          title="Recent price changes"
          subtitle="Detected by collection runs"
          actions={<Link className="btn sm" to="/price-history">View history</Link>}
        >
          {data.recent.price_changes.length === 0 ? (
            <div className="empty">No price changes recorded yet</div>
          ) : (
            <div className="stack tight">
              {data.recent.price_changes.map((item) => (
                <div key={item.id} className="inline" style={{ justifyContent: 'space-between' }}>
                  <div>
                    <Link className="row-title" to={`/listings/${item.id}`}>
                      {item.title}
                    </Link>
                    <div className="row-sub">{item.source_name}</div>
                  </div>
                  <div className="right">
                    <div className="row-title">{money(item.price, item.currency)}</div>
                    <div className="row-sub">{relative(item.changed_at)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Recent searches" subtitle="Your latest unified searches">
          {data.recent.searches.length === 0 ? (
            <div className="empty">No searches yet</div>
          ) : (
            <div className="stack tight">
              {data.recent.searches.map((item) => (
                <div key={item.id} className="inline" style={{ justifyContent: 'space-between' }}>
                  <div>
                    <div className="row-title">{item.query_text || 'Filter-only search'}</div>
                    <div className="row-sub">
                      {titleCase(item.mode)} · {relative(item.created_at)}
                    </div>
                  </div>
                  <Badge variant="info">{item.result_count} results</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid cols-2">
        <Card
          title="Notifications"
          actions={<Link className="btn sm" to="/notifications">Open inbox</Link>}
        >
          {data.recent.notifications.length === 0 ? (
            <div className="empty">Nothing new</div>
          ) : (
            <div className="stack tight">
              {data.recent.notifications.map((item) => (
                <div key={item.id}>
                  <div className="inline" style={{ justifyContent: 'space-between' }}>
                    <strong>{item.title}</strong>
                    <Badge variant={tone(item.level)}>{item.level}</Badge>
                  </div>
                  <div className="row-sub">{relative(item.created_at)}</div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Background jobs"
          actions={<Link className="btn sm" to="/jobs">Manage jobs</Link>}
        >
          {data.recent.jobs.length === 0 ? (
            <div className="empty">No job runs yet — start the worker service</div>
          ) : (
            <div className="stack tight">
              {data.recent.jobs.map((job) => (
                <div key={job.id} className="inline" style={{ justifyContent: 'space-between' }}>
                  <div>
                    <div className="row-title">{titleCase(job.job_type)}</div>
                    <div className="row-sub">
                      {relative(job.started_at)} · {job.trigger}
                    </div>
                  </div>
                  <div className="right">
                    <Badge variant={tone(job.status)}>{job.status}</Badge>
                    <div className="row-sub">{job.duration_ms ? `${job.duration_ms} ms` : ''}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Quick actions" subtitle="Common operator tasks">
        <div className="inline">
          <button type="button" className="btn" onClick={() => navigate('/sources')}>
            Review sources
          </button>
          <button type="button" className="btn" onClick={() => navigate('/api-management')}>
            Configure APIs
          </button>
          <button type="button" className="btn" onClick={() => navigate('/listings/flagged')}>
            Review flagged listings
          </button>
          <button type="button" className="btn" onClick={() => navigate('/backups')}>
            Database backups
          </button>
        </div>
      </Card>
    </>
  );
}
