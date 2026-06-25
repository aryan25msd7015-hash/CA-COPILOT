"""
SQLAlchemy ORM models for the CA Intelligence Platform.

Importing this package ensures all models are registered with Base.metadata,
which is required for Alembic autogenerate and explicit migrations.
"""

from .organization import Organization
from .user import TeamInvitation, User
from .refresh_token import RefreshToken
from .system import OrganizationAgentState, SystemAuditLog, SystemEvent
from .client import Client
from .document import Document, DocumentExtraction, DocumentPipelineEvent
from .transaction import Transaction
from .legal_chunk import LegalChunk
from .compliance_deadline import ComplianceDeadline
from .whatsapp_reminder import WhatsAppReminder
from .reconciliation import ReconciliationConfig, ReconciliationMatchAction, ReconciliationResult
from .health_history import ClientHealthHistory, ClientHealthScoreEvent
from .anomaly_flag import AnomalyFlag
from .saved_query import SavedQuery
from .autopilot import (
    AutopilotException, AutopilotFollowup, AutopilotReviewAction, AutopilotSyncRun,
)
from .extensions import (
    BankFacility, CertificateRecord, DeadlineClientMap, DebtorItem,
    DrawingPowerStatement, FirmCredential, InventoryItem, LeaseRecord,
    MsmePaymentViolation, MsmeVendor, RfpBid, SecretarialDocument,
    TimesheetEntry, UserActivityLog,
)
from .practice_ops import (
    AttendanceEntry, BillingPlan, ClientPortalContact, CredentialVaultItem,
    DaybookEntry, ImportJob, PaymentReceipt, PortalRequest, PracticeInvoice,
    PracticeTask, SavedView,
)

__all__ = [
    "Organization",
    "User",
    "TeamInvitation",
    "RefreshToken",
    "SystemAuditLog",
    "SystemEvent",
    "OrganizationAgentState",
    "Client",
    "Document",
    "DocumentExtraction",
    "DocumentPipelineEvent",
    "Transaction",
    "LegalChunk",
    "ComplianceDeadline",
    "WhatsAppReminder",
    "ReconciliationConfig",
    "ReconciliationMatchAction",
    "ReconciliationResult",
    "ClientHealthHistory",
    "ClientHealthScoreEvent",
    "AnomalyFlag",
    "SavedQuery",
    "AutopilotSyncRun",
    "AutopilotException",
    "AutopilotReviewAction",
    "AutopilotFollowup",
    "DeadlineClientMap",
    "MsmeVendor",
    "MsmePaymentViolation",
    "BankFacility",
    "InventoryItem",
    "DebtorItem",
    "DrawingPowerStatement",
    "CertificateRecord",
    "SecretarialDocument",
    "LeaseRecord",
    "FirmCredential",
    "RfpBid",
    "UserActivityLog",
    "TimesheetEntry",
    "PracticeTask",
    "DaybookEntry",
    "BillingPlan",
    "PracticeInvoice",
    "PaymentReceipt",
    "ClientPortalContact",
    "PortalRequest",
    "AttendanceEntry",
    "CredentialVaultItem",
    "ImportJob",
    "SavedView",
]
