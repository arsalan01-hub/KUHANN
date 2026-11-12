import { useState } from 'react';
import { api } from '../api/client';
import { BarChart } from '../components/charts';
import { Card, ErrorBox, Field, Loading, Stat } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { money, number, titleCase } from '../lib/format';

interface Dimension {
  key: string;
  count: number;
  average_price_eur: number | null;
  min_price_eur: number | null;
  max_price_eur: number | null;
}

interface Summary {
  sample_size: number;
  average_price_eur: number | null;
  min_price_eur: number | null;
  max_price_eur: number | null;
  average_mileage_km: number | null;
  average_year: number | null;
  disclaimer: string;
  by_dimension: Record<string, Dimension[]>;
}

export default function PriceAnalysis() {
  const [manufacturer, setManufacturer] = useState('');
  const [country, setCountry] = useState('');
  const [years, setYears] = useState('');

  const { data, loading, error, reload } = useApi<Summary>(
    () => api.get<Summary>('/price/summary', { manufacturer, country, year_min: years }),
    [manufacturer, country, years],
  );

  return (
    <>
      <div className="page-head">
        <div className="grow">
          <h1>Price analysis</h1>
          <p>
            Aggregate asking-price statistics computed from collected advertisements. Original currencies
            are preserved; comparison figures are converted to EUR.
          </p>
        </div>
      </div>

      <Card title="Cohort" subtitle="Adjust the comparison group">
        <div className="filter-grid">
          <Field label="Manufacturer">
            <select value={manufacturer} onChange={(event) => setManufacturer(event.target.value)}>
              <option value="">All manufacturers</option>
              {(data?.by_dimension.manufacturer ?? []).map((item) => (
                <option key={item.key} value={item.key}>
                  {item.key}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Country">
            <select value={country} onChange={(event) => setCountry(event.target.value)}>
              <option value="">All countries</option>
              {(data?.by_dimension.country ?? []).map((item) => (
                <option key={item.key} value={item.key}>
                  {item.key}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Registered from">
            <input
              type="number"
              placeholder="2016"
              value={years}
              onChange={(event) => setYears(event.target.value)}
            />
          </Field>
        </div>
      </Card>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data ? (
        <Loading />
      ) : data ? (
        <>
          <div className="stat-grid">
            <Stat label="Sample size" value={number(data.sample_size)} hint="Listings with a usable price" />
            <Stat label="Average asking price" value={money(data.average_price_eur)} />
            <Stat label="Lowest asking price" value={money(data.min_price_eur)} />
            <Stat label="Highest asking price" value={money(data.max_price_eur)} />
            <Stat label="Average mileage" value={data.average_mileage_km ? `${number(data.average_mileage_km)} km` : '—'} />
            <Stat label="Average production year" value={data.average_year ?? '—'} />
          </div>

          <div className="alert info">{data.disclaimer}</div>

          <div className="grid cols-2">
            <Card title="Average price by manufacturer">
              <BarChart
                items={(data.by_dimension.manufacturer ?? []).map((item) => ({
                  label: item.key,
                  value: Math.round(item.average_price_eur ?? 0),
                }))}
                format={(value) => money(value)}
              />
            </Card>
            <Card title="Average price by country">
              <BarChart
                items={(data.by_dimension.country ?? []).map((item) => ({
                  label: item.key,
                  value: Math.round(item.average_price_eur ?? 0),
                }))}
                format={(value) => money(value)}
                color="var(--success)"
              />
            </Card>
          </div>

          <Card title="Detailed comparison" subtitle="Volume, average, minimum and maximum asking price">
            {(['manufacturer', 'country', 'year'] as const).map((dimension) => (
              <div key={dimension} className="stack tight">
                <h3>{titleCase(dimension)}</h3>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>{titleCase(dimension)}</th>
                        <th className="numeric">Listings</th>
                        <th className="numeric">Average</th>
                        <th className="numeric">Minimum</th>
                        <th className="numeric">Maximum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(data.by_dimension[dimension] ?? []).map((item) => (
                        <tr key={item.key}>
                          <td className="row-title">{item.key}</td>
                          <td className="numeric">{item.count}</td>
                          <td className="numeric">{money(item.average_price_eur)}</td>
                          <td className="numeric">{money(item.min_price_eur)}</td>
                          <td className="numeric">{money(item.max_price_eur)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </Card>
        </>
      ) : null}
    </>
  );
}
