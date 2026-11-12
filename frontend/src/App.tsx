import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { Loading } from './components/ui';
import { useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import SearchPage from './pages/SearchPage';
import Listings from './pages/Listings';
import NewListings from './pages/NewListings';
import SavedTrucks from './pages/SavedTrucks';
import SavedSearches from './pages/SavedSearches';
import PriceAnalysis from './pages/PriceAnalysis';
import PriceHistory from './pages/PriceHistory';
import Sources from './pages/Sources';
import SourceDetail from './pages/SourceDetail';
import Discovery from './pages/Discovery';
import AddWebsite from './pages/AddWebsite';
import ApiManagement from './pages/ApiManagement';
import SearchHistoryPage from './pages/SearchHistory';
import NotificationsPage from './pages/Notifications';
import Users from './pages/Users';
import Roles from './pages/Roles';
import Settings from './pages/Settings';
import AuditLogs from './pages/AuditLogs';
import Jobs from './pages/Jobs';
import Health from './pages/Health';
import Backups from './pages/Backups';
import ListingDetail from './pages/ListingDetail';
import Profile from './pages/Profile';
import NotFound from './pages/NotFound';

function Protected() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div style={{ padding: 40 }}>
        <Loading label="Preparing your workspace…" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Layout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/listings" element={<Listings />} />
        <Route path="/listings/new" element={<NewListings />} />
        <Route path="/listings/:listingId" element={<ListingDetail />} />
        <Route path="/saved" element={<SavedTrucks kind="saved" />} />
        <Route path="/favorites" element={<SavedTrucks kind="favorite" />} />
        <Route path="/saved-searches" element={<SavedSearches />} />
        <Route path="/price-analysis" element={<PriceAnalysis />} />
        <Route path="/price-history" element={<PriceHistory />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/sources/:sourceId" element={<SourceDetail />} />
        <Route path="/discovery" element={<Discovery />} />
        <Route path="/add-website" element={<AddWebsite />} />
        <Route path="/api-management" element={<ApiManagement />} />
        <Route path="/search-history" element={<SearchHistoryPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/users" element={<Users />} />
        <Route path="/roles" element={<Roles />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/audit" element={<AuditLogs />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/health" element={<Health />} />
        <Route path="/backups" element={<Backups />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
