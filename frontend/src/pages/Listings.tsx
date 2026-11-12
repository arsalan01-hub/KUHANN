import ListingsBrowser from '../components/ListingsBrowser';

export default function Listings() {
  return (
    <ListingsBrowser
      endpoint="/listings"
      title="All listings"
      description="Every external truck advertisement collected by KUHHAN, with its original source and URL preserved."
    />
  );
}
