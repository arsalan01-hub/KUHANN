"""Import every model so Alembic and ``Base.metadata`` see the full schema."""

from app.models.api import ApiFieldMapping, ApiIntegration, ApiSyncLog  # noqa: F401
from app.models.listing import (  # noqa: F401
    DuplicateCandidate,
    Listing,
    ListingImage,
    PriceHistory,
    RiskAssessment,
    SavedListing,
)
from app.models.search import SavedSearch, SearchHistory  # noqa: F401
from app.models.source import DiscoveryHit, DiscoveryRun, WebsiteSource  # noqa: F401
from app.models.system import (  # noqa: F401
    AuditLog,
    Backup,
    JobRun,
    JobSchedule,
    Notification,
    SystemSetting,
)
from app.models.user import Permission, Role, User, role_permissions, user_roles  # noqa: F401
