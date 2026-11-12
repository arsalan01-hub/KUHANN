import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { tone } from '../lib/format';

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = '',
  padded = true,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={`card ${className}`} style={padded ? undefined : { padding: 0 }}>
      {(title || actions) && (
        <header className="card-head">
          <div className="grow">
            {title && <h2>{title}</h2>}
            {subtitle && <div className="card-sub">{subtitle}</div>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}

export function Badge({ children, variant }: { children: ReactNode; variant?: string }) {
  return <span className={`badge ${variant ?? 'neutral'} dot`}>{children}</span>;
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const label = (status ?? 'unknown').replace(/_/g, ' ');
  return <span className={`badge ${tone(status)} dot`}>{label}</span>;
}

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />;
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading-row">
      <Spinner /> {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="alert error">
      {message}
      {onRetry && (
        <>
          {' '}
          <button type="button" className="link-btn" onClick={onRetry}>
            Retry
          </button>
        </>
      )}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {hint && <span className="small">{hint}</span>}
    </div>
  );
}

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  numeric?: boolean;
  width?: string;
}

export function DataTable<T>({
  columns,
  rows,
  empty = 'Nothing to show yet',
  getKey,
}: {
  columns: Column<T>[];
  rows: T[] | null | undefined;
  empty?: string;
  getKey: (row: T, index: number) => string;
}) {
  if (!rows || rows.length === 0) return <Empty title={empty} />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.numeric ? 'numeric' : ''} style={column.width ? { width: column.width } : undefined}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={getKey(row, index)}>
              {columns.map((column) => (
                <td key={column.key} className={column.numeric ? 'numeric' : ''}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  if (!total) return null;
  return (
    <div className="pagination">
      <button type="button" className="btn sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {Math.max(pages, 1)} · {total} record(s) · {pageSize} per page
      </span>
      <button
        type="button"
        className="btn sm"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </div>
  );
}

export function Modal({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" onMouseDown={onClose}>
      <div className={`modal ${wide ? 'wide' : ''}`} onMouseDown={(event) => event.stopPropagation()}>
        <div className="card-head">
          <div className="grow">
            <h2>{title}</h2>
            {subtitle && <div className="card-sub">{subtitle}</div>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {children}
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: T; label: string }[];
  active: T;
  onChange: (key: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={active === tab.key}
          className={`tab ${active === tab.key ? 'active' : ''}`}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------- toasts
interface ToastMessage {
  id: number;
  text: string;
  kind: 'info' | 'success' | 'error';
}

const ToastContext = createContext<{ push: (text: string, kind?: ToastMessage['kind']) => void } | null>(
  null,
);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);
  const push = useCallback((text: string, kind: ToastMessage['kind'] = 'info') => {
    const id = Date.now() + Math.random();
    setMessages((current) => [...current, { id, text, kind }]);
    window.setTimeout(() => {
      setMessages((current) => current.filter((item) => item.id !== id));
    }, 5200);
  }, []);
  const value = useMemo(() => ({ push }), [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {messages.map((message) => (
          <div key={message.id} className={`toast ${message.kind}`}>
            {message.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside ToastProvider');
  return context;
}
