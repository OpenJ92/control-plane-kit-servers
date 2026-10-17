"""Maintained public topology client for cpk-server."""

from .journal import JournalError, JournalStore, canonical_operation_ref
from .profile import ClientConfigurationError, ClientProfile, load_profile
from .transport import (
    ClientAuthorizationError,
    ClientTransportError,
    PublicHttpTransport,
)
from .workflow import ClientInputError, ClientResult, SavedDesiredRevision, TopologyClient
from .catalogue import CatalogueResult
from .report import ReportResult


_AUTHORING_EXPORTS = frozenset({
    "AuthoredDesiredGraph",
    "GatewayHealthRoutes",
    "GatewayHealthTargetIntent",
    "PendingReceiverContinuation",
    "ReceiverAuthoringError",
    "ReceiverIntroduction",
    "ReceiverScope",
})


def __getattr__(name: str):
    if name not in _AUTHORING_EXPORTS:
        raise AttributeError(name)
    from . import authoring
    return getattr(authoring, name)


__all__ = (
    "AuthoredDesiredGraph",
    "CatalogueResult",
    "GatewayHealthRoutes",
    "GatewayHealthTargetIntent",
    "ReportResult",
    "ClientAuthorizationError",
    "ClientConfigurationError",
    "ClientInputError",
    "ClientProfile",
    "ClientResult",
    "ClientTransportError",
    "JournalError",
    "JournalStore",
    "PendingReceiverContinuation",
    "PublicHttpTransport",
    "ReceiverAuthoringError",
    "ReceiverIntroduction",
    "ReceiverScope",
    "TopologyClient",
    "SavedDesiredRevision",
    "canonical_operation_ref",
    "load_profile",
)
