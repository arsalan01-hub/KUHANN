import ListingsBrowser from '../components/ListingsBrowser';

export default function NewListings() {
  return (
    <ListingsBrowser
      endpoint="/listings/new"
      title="New listings"
      description="Listings first discovered inside the monitoring window, newest first."
      extraQuery={{ status: 'active' }}
    />
  );
}
