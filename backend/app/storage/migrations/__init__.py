"""Ordered, immutable SQLite migrations for BidRadar-X storage."""

from .v0001_prototype_baseline import CHECKSUM as V0001_CHECKSUM
from .v0001_prototype_baseline import upgrade as upgrade_v0001
from .v0002_provenance_models import CHECKSUM as V0002_CHECKSUM
from .v0002_provenance_models import upgrade as upgrade_v0002
from .v0003_legacy_workflow_compatibility import CHECKSUM as V0003_CHECKSUM
from .v0003_legacy_workflow_compatibility import upgrade as upgrade_v0003
from .v0004_contract_history import CHECKSUM as V0004_CHECKSUM
from .v0004_contract_history import upgrade as upgrade_v0004
from .v0005_source_publication_identity import CHECKSUM as V0005_CHECKSUM
from .v0005_source_publication_identity import upgrade as upgrade_v0005
from .v0006_hidden_report_runs import CHECKSUM as V0006_CHECKSUM
from .v0006_hidden_report_runs import upgrade as upgrade_v0006
from .v0007_daily_spend_guard import CHECKSUM as V0007_CHECKSUM
from .v0007_daily_spend_guard import upgrade as upgrade_v0007
from .v0008_history_duplicate_tombstones import CHECKSUM as V0008_CHECKSUM
from .v0008_history_duplicate_tombstones import upgrade as upgrade_v0008
from .v0009_interval_subscriptions import CHECKSUM as V0009_CHECKSUM
from .v0009_interval_subscriptions import upgrade as upgrade_v0009
from .v0010_external_delivery_outbox import CHECKSUM as V0010_CHECKSUM
from .v0010_external_delivery_outbox import upgrade as upgrade_v0010


MIGRATION_SPECS = (
    (1, "prototype_baseline", V0001_CHECKSUM, upgrade_v0001),
    (2, "provenance_models", V0002_CHECKSUM, upgrade_v0002),
    (3, "legacy_workflow_compatibility", V0003_CHECKSUM, upgrade_v0003),
    (4, "contract_history", V0004_CHECKSUM, upgrade_v0004),
    (5, "source_publication_identity", V0005_CHECKSUM, upgrade_v0005),
    (6, "hidden_report_runs", V0006_CHECKSUM, upgrade_v0006),
    (7, "daily_spend_guard", V0007_CHECKSUM, upgrade_v0007),
    (8, "history_duplicate_tombstones", V0008_CHECKSUM, upgrade_v0008),
    (9, "interval_subscriptions", V0009_CHECKSUM, upgrade_v0009),
    (10, "external_delivery_outbox", V0010_CHECKSUM, upgrade_v0010),
)
