interface Point {
  label: string;
  value: number;
}

const PALETTE = ['#0f4c81', '#2f7fc1', '#4cc38a', '#e0a33a', '#b02318', '#7a5af8', '#0e7490', '#9a6208'];

export function LineChart({
  points,
  height = 180,
  format = (value: number) => String(value),
}: {
  points: Point[];
  height?: number;
  format?: (value: number) => string;
}) {
  if (!points.length) {
    return <div className="empty">No data recorded yet</div>;
  }
  const width = 640;
  const padding = { top: 14, right: 12, bottom: 26, left: 44 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const max = Math.max(...points.map((point) => point.value), 1);
  const step = points.length > 1 ? innerWidth / (points.length - 1) : innerWidth;

  const coordinates = points.map((point, index) => ({
    x: padding.left + index * step,
    y: padding.top + innerHeight - (point.value / max) * innerHeight,
    ...point,
  }));
  const line = coordinates.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  const area = `${padding.left},${padding.top + innerHeight} ${line} ${(padding.left + innerWidth).toFixed(1)},${padding.top + innerHeight}`;

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Trend chart">
      {[0, 0.5, 1].map((fraction) => {
        const y = padding.top + innerHeight * fraction;
        return (
          <g key={fraction}>
            <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="var(--border)" strokeWidth="1" />
            <text x={padding.left - 8} y={y + 4} textAnchor="end" fontSize="10" fill="var(--muted)">
              {format(Math.round(max * (1 - fraction)))}
            </text>
          </g>
        );
      })}
      <polygon points={area} fill="var(--accent)" opacity="0.10" />
      <polyline points={line} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
      {coordinates.map((point, index) => (
        <circle key={`${point.label}-${index}`} cx={point.x} cy={point.y} r="3" fill="var(--accent)">
          <title>{`${point.label}: ${format(point.value)}`}</title>
        </circle>
      ))}
      {coordinates
        .filter((_, index) => index % Math.ceil(coordinates.length / 7) === 0)
        .map((point) => (
          <text key={`label-${point.label}-${point.x}`} x={point.x} y={height - 6} textAnchor="middle" fontSize="10" fill="var(--muted)">
            {point.label}
          </text>
        ))}
    </svg>
  );
}

export function BarChart({
  items,
  format = (value: number) => String(value),
  color = 'var(--accent)',
}: {
  items: Point[];
  format?: (value: number) => string;
  color?: string;
}) {
  if (!items.length) return <div className="empty">No data recorded yet</div>;
  const max = Math.max(...items.map((item) => item.value), 1);
  return (
    <div className="stack tight">
      {items.map((item) => (
        <div key={item.label} className="stack tight">
          <div className="inline" style={{ justifyContent: 'space-between' }}>
            <span className="small">{item.label}</span>
            <span className="small mono">{format(item.value)}</span>
          </div>
          <div className="progress">
            <span style={{ width: `${Math.max(2, (item.value / max) * 100)}%`, background: color }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function Donut({
  segments,
  size = 150,
}: {
  segments: Point[];
  size?: number;
}) {
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  if (!total) return <div className="empty">No data recorded yet</div>;
  const radius = size / 2 - 12;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="inline" style={{ gap: 16, alignItems: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Distribution">
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          {segments.map((segment, index) => {
            const length = (segment.value / total) * circumference;
            const circle = (
              <circle
                key={segment.label}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke={PALETTE[index % PALETTE.length]}
                strokeWidth="16"
                strokeDasharray={`${length} ${circumference - length}`}
                strokeDashoffset={-offset}
              />
            );
            offset += length;
            return circle;
          })}
        </g>
      </svg>
      <div className="stack tight small">
        {segments.map((segment, index) => (
          <span key={segment.label} className="inline" style={{ gap: 6 }}>
            <span
              style={{
                width: 9,
                height: 9,
                borderRadius: 3,
                background: PALETTE[index % PALETTE.length],
                display: 'inline-block',
              }}
            />
            {segment.label} <span className="muted">({segment.value})</span>
          </span>
        ))}
      </div>
    </div>
  );
}
