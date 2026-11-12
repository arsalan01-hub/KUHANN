export interface Role {
  id: string;
  name: string;
  description: string;
  is_system: boolean;
  permission_codes?: string[];
  user_count?: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  totp_enabled: boolean;
  last_login_at: string | null;
  locked_until?: string | null;
  failed_login_count?: number;
  created_at: string;
  roles: Role[];
  permission_codes: string[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Listing {
  id: string;
  source_id: string;
  source_name: string;
  original_url: string;
  external_id?: string;
  manufacturer: string | null;
  model: string | null;
  year: number | null;
  price: number | null;
  currency: string;
  price_eur: number | null;
  mileage_km: number | null;
  power_hp: number | null;
  axle_config: string | null;
  axles_count: number | null;
  euro_class: string | null;
  transmission: string | null;
  fuel_type: string | null;
  cab_type: string | null;
  condition: string | null;
  country: string | null;
  city: string | null;
  primary_image_url: string | null;
  image_count: number;
  listing_status: string;
  extraction_status: string;
  completeness_pct: number;
  missing_fields: string[];
  validation_warnings: string[];
  risk_score: number;
  risk_reasons: string[];
  risk_reviewed: boolean;
  first_discovered_at: string;
  last_checked_at: string | null;
  last_price_change_at: string | null;
  unavailable_since?: string | null;
  images: string[];
  title?: string;
  description?: string;
  saved_id?: string;
  saved_kind?: string;
  price_history?: { price: number; currency: string; price_eur: number | null; recorded_at: string; reason: string }[];
  duplicates?: { id: string; score: number; reasons: string[]; status: string; other_listing_id: string }[];
  source?: { id: string; name: string; domain: string; status: string; homepage_url: string; terms_url: string | null };
}

export interface SearchResponse extends Page<Listing> {
  mode: string;
  sort: string;
  source_status: SourceStatus[];
  duration_ms: number;
  notes: string[];
  disclaimer: string;
}

export interface SourceStatus {
  source_id: string;
  name: string;
  domain: string;
  status: string;
  operational: boolean;
  last_run_status: string | null;
  last_collected_at: string | null;
  last_error: string | null;
  searchable: boolean;
}

export interface WebsiteSource {
  id: string;
  domain: string;
  name: string;
  homepage_url: string;
  listing_url: string | null;
  country: string | null;
  language: string | null;
  category: string;
  status: string;
  access_method: string;
  connector_key: string | null;
  connector_config: Record<string, unknown>;
  robots_url: string | null;
  robots_allows_crawl: boolean | null;
  robots_notes: string;
  terms_url: string | null;
  api_doc_url: string | null;
  has_official_api: boolean | null;
  truck_evidence: Record<string, unknown>;
  compatibility: Record<string, unknown>;
  analysis_report: Record<string, unknown>;
  discovery_provider: string;
  discovery_query: string | null;
  discovered_at: string | null;
  approved_at: string | null;
  review_note: string;
  last_checked_at: string | null;
  last_collected_at: string | null;
  last_run_status: string | null;
  last_error: string | null;
  consecutive_failures: number;
  listings_collected: number;
  listing_count?: number;
  active_listing_count?: number;
  created_at: string;
  updated_at: string;
}

export interface ApiIntegration {
  id: string;
  name: string;
  provider_name: string;
  purpose: string;
  website_source_id: string | null;
  base_url: string;
  endpoint_path: string;
  api_version: string;
  http_method: string;
  auth_type: string;
  header_name: string;
  custom_headers: Record<string, string>;
  query_params: Record<string, string>;
  body_template: Record<string, unknown>;
  has_credentials: boolean;
  credential_fields: Record<string, string>;
  pagination_type: string;
  page_parameter: string;
  page_size_parameter: string;
  page_size: number;
  max_pages: number;
  records_path: string;
  rate_limit_per_minute: number;
  timeout_seconds: number;
  response_format: string;
  status: string;
  doc_url: string | null;
  last_test_at: string | null;
  last_test_status: string | null;
  last_test_message: string | null;
  last_success_at: string | null;
  last_error: string | null;
  last_response_snippet: string | null;
  last_response_ms: number | null;
  requests_total: number;
  errors_total: number;
  records_synced: number;
  created_at: string;
  mappings: Mapping[];
}

export interface Mapping {
  id?: string;
  external_field: string;
  kuhhan_field: string;
  transform: string;
  required: boolean;
  default_value: string | null;
}

export interface SavedSearch {
  id: string;
  user_id: string;
  name: string;
  mode: string;
  filters: Record<string, unknown>;
  source_ids: string[];
  schedule: string;
  notify: boolean;
  is_active: boolean;
  last_run_at: string | null;
  last_match_count: number;
  total_matches: number;
  created_at: string;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  level: string;
  category: string;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface JobRun {
  id: string;
  job_type: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  trigger: string;
  message: string;
  detail: Record<string, unknown>;
}

export interface JobSchedule {
  id: string;
  name: string;
  job_type: string;
  interval_seconds: number;
  enabled: boolean;
  config: Record<string, unknown>;
  last_run_at: string | null;
  last_status: string | null;
  last_message: string | null;
  next_run_at: string | null;
}

export interface AuditEntry {
  id: string;
  user_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  ip_address: string | null;
  outcome: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface BackupRecord {
  id: string;
  filename: string;
  method: string;
  status: string;
  size_bytes: number;
  checksum_sha256: string | null;
  table_count: number;
  row_count: number;
  message: string;
  verified_at: string | null;
  created_at: string;
}

export interface DashboardData {
  totals: Record<string, number | null>;
  charts: {
    listings_by_day: { date: string; count: number }[];
    price_by_manufacturer: { manufacturer: string; count: number; avg_price_eur: number }[];
    listings_by_country: { country: string; count: number }[];
    sources_by_status: { status: string; count: number }[];
  };
  recent: {
    price_changes: { id: string; title: string; price: number | null; currency: string; price_eur: number | null; changed_at: string; source_name: string }[];
    searches: { id: string; query_text: string; mode: string; result_count: number; created_at: string; duration_ms: number }[];
    notifications: Notification[];
    jobs: JobRun[];
  };
  unread_notifications: number;
  generated_at: string;
}
