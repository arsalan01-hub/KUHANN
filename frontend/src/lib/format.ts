export function money(value: number | null | undefined, currency = 'EUR'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function number(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('en-IE').format(value);
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${Math.round(value)}%`;
}

export function date(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function relative(value: string | null | undefined): string {
  if (!value) return 'never';
  const parsed = new Date(value).getTime();
  if (Number.isNaN(parsed)) return 'never';
  const diff = Date.now() - parsed;
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return date(value);
}

export function bytes(value: number | null | undefined): string {
  if (!value) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return '—';
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export const STATUS_TONES: Record<string, string> = {
  active: 'success',
  approved: 'success',
  success: 'success',
  completed: 'success',
  verified: 'success',
  disabled: 'neutral',
  unknown: 'neutral',
  manual_access_only: 'warning',
  needs_review: 'warning',
  under_investigation: 'warning',
  newly_discovered: 'info',
  temporarily_unavailable: 'warning',
  restricted: 'danger',
  rejected: 'danger',
  failed: 'danger',
  unsupported: 'danger',
  running: 'info',
  draft: 'neutral',
  unreachable: 'warning',
  removed: 'danger',
  inactive: 'neutral',
};

export function tone(status: string | null | undefined): string {
  if (!status) return 'neutral';
  return STATUS_TONES[status] ?? 'neutral';
}
