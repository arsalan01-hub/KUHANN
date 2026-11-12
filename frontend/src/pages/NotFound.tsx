import { Link } from 'react-router-dom';
import { Card } from '../components/ui';

export default function NotFound() {
  return (
    <Card title="Page not found">
      <p className="muted">This address does not exist in KUHHAN.</p>
      <div>
        <Link className="btn primary" to="/">
          Back to dashboard
        </Link>
      </div>
    </Card>
  );
}
