import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { LineChart } from '../components/charts';
import { Card, DataTable, ErrorBox, Field, Loading } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { date, dateTime, money } from '../lib/format';

interface HistoryResponse {
  days: number;
  series: { date: string; average_price_eur: number | null; observations: number }[];
  recent_changes: { id: string; listing_id: string; price: number; currency: string; price_eur: number | null; recorded_at: string; reason: string }[];
  disclaimer: string;
}

export default function PriceHistory() {
  const [days, setDays] = useState(90);
  const { data, loading, error, reload } = useApi<HistoryResponse>(
    () => api.get<HistoryResponse>('/price/history', { days }),
    [days],
  );

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Price history</h1>
          <p>Average asking price per day across observed advertisements, plus every recorded price change.</p>
        </div>
        <div className="head-actions" style={{ minWidth: 160 }}>
          <Field label="Period">
            <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 180 days</option>
              <option value={365}>Last year</option>
              <option value={730}>Last 2 years</option>
            </select>
          </Field>
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data ? (
        <Loading />
      ) : data ? (
        <>
          <Card title="Average asking price" subtitle={`${data.series.length} observation day(s)`}>
            <LineChart
              points={data.series.map((point) => ({
                label: point.date.slice(5),
                value: Math.round(point.average_price_eur ?? 0),
              }))}
              format={(value) => money(value)}
            />
            <p className="small muted">{data.disclaimer}</p>
          </Card>

          <Card title="Recorded price changes" subtitle="Every change detected by a collection run">
            <DataTable
              rows={data.recent_changes}
              getKey={(row) => row.id}
              empty="No price changes recorded in this period"
              columns={[
                {
                  key: 'listing',
                  header: 'Listing',
                  render: (row) => (
                    <Link className="row-title" to={`/listings/${row.listing_id}`}>
                      Open listing
                    </Link>
                  ),
                },
                {
                  key: 'price',
                  header: 'Recorded price',
                  numeric: true,
                  render: (row) => money(row.price, row.currency),
                },
                {
                  key: 'eur',
                  header: 'In EUR',
                  numeric: true,
                  render: (row) => money(row.price_eur),
                },
                { key: 'reason', header: 'Reason', render: (row) => row.reason },
                { key: 'when', header: 'Recorded', render: (row) => dateTime(row.recorded_at) },
              ]}
            />
          </Card>

          {data.series.length > 0 && (
            <Card title="Daily observations">
              <DataTable
                rows={data.series}
                getKey={(row) => row.date}
                columns={[
                  { key: 'date', header: 'Date', render: (row) => date(row.date) },
                  { key: 'avg', header: 'Average asking price', numeric: true, render: (row) => money(row.average_price_eur) },
                  { key: 'obs', header: 'Observations', numeric: true, render: (row) => row.observations },
                ]}
              />
            </Card>
          )}
        </>
      ) : null}
    </>
  );
}
