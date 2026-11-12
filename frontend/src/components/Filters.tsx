import type { ReactNode } from 'react';
import { Field } from './ui';

export type FilterValues = Record<string, string>;

export const EMPTY_FILTERS: FilterValues = {
  q: '',
  manufacturer: '',
  model: '',
  year_min: '',
  year_max: '',
  price_min: '',
  price_max: '',
  mileage_max: '',
  power_min: '',
  power_max: '',
  country: '',
  euro_class: '',
  transmission: '',
  fuel_type: '',
  axle_config: '',
  condition: '',
  status: '',
  city: '',
};

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 45 }, (_, index) => CURRENT_YEAR + 1 - index);

export function FilterPanel({
  values,
  onChange,
  onSubmit,
  onReset,
  manufacturers,
  countries,
  children,
  busy,
}: {
  values: FilterValues;
  onChange: (values: FilterValues) => void;
  onSubmit: () => void;
  onReset: () => void;
  manufacturers?: { value: string; count: number }[];
  countries?: { value: string; count: number }[];
  children?: ReactNode;
  busy?: boolean;
}) {
  const set = (key: keyof FilterValues) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    onChange({ ...values, [key]: event.target.value });

  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="filter-grid">
        <Field label="Keyword">
          <input placeholder="Actros, TGX, FH…" value={values.q} onChange={set('q')} />
        </Field>
        <Field label="Manufacturer">
          <select value={values.manufacturer} onChange={set('manufacturer')}>
            <option value="">Any</option>
            {(manufacturers ?? []).map((item) => (
              <option key={item.value} value={item.value}>
                {item.value} ({item.count})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Model">
          <input placeholder="Actros 1848" value={values.model} onChange={set('model')} />
        </Field>
        <Field label="Year from">
          <select value={values.year_min} onChange={set('year_min')}>
            <option value="">Any</option>
            {YEARS.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Year to">
          <select value={values.year_max} onChange={set('year_max')}>
            <option value="">Any</option>
            {YEARS.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Price from (EUR)">
          <input type="number" min="0" step="500" value={values.price_min} onChange={set('price_min')} />
        </Field>
        <Field label="Price to (EUR)">
          <input type="number" min="0" step="500" value={values.price_max} onChange={set('price_max')} />
        </Field>
        <Field label="Max mileage (km)">
          <input type="number" min="0" step="10000" value={values.mileage_max} onChange={set('mileage_max')} />
        </Field>
        <Field label="Power from (hp)">
          <input type="number" min="0" step="10" value={values.power_min} onChange={set('power_min')} />
        </Field>
        <Field label="Power to (hp)">
          <input type="number" min="0" step="10" value={values.power_max} onChange={set('power_max')} />
        </Field>
        <Field label="Country">
          <select value={values.country} onChange={set('country')}>
            <option value="">Any</option>
            {(countries ?? []).map((item) => (
              <option key={item.value} value={item.value}>
                {item.value} ({item.count})
              </option>
            ))}
          </select>
        </Field>
        <Field label="City">
          <input value={values.city} onChange={set('city')} placeholder="Vilnius" />
        </Field>
        <Field label="Emission class">
          <select value={values.euro_class} onChange={set('euro_class')}>
            <option value="">Any</option>
            {['Euro 3', 'Euro 4', 'Euro 5', 'Euro 6', 'Euro 6d'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Transmission">
          <select value={values.transmission} onChange={set('transmission')}>
            <option value="">Any</option>
            {['Automatic', 'Manual', 'Semi-automatic'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Fuel">
          <select value={values.fuel_type} onChange={set('fuel_type')}>
            <option value="">Any</option>
            {['Diesel', 'Electric', 'Hybrid', 'LNG', 'CNG'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Axle configuration">
          <select value={values.axle_config} onChange={set('axle_config')}>
            <option value="">Any</option>
            {['4x2', '6x2', '6x4', '8x4', '4x4'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Condition">
          <select value={values.condition} onChange={set('condition')}>
            <option value="">Any</option>
            {['Used', 'New', 'Damaged'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Listing status">
          <select value={values.status} onChange={set('status')}>
            <option value="">Any</option>
            {['active', 'inactive', 'unreachable', 'removed', 'unknown'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {children}
      <div className="inline">
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? 'Searching…' : 'Apply filters'}
        </button>
        <button type="button" className="btn" onClick={onReset}>
          Reset
        </button>
      </div>
    </form>
  );
}
