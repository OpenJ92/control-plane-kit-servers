"""cpk-server product wrapper composition surface."""

from .boundary import (
    CpkServerApplicationBoundary,
    CpkServerBoundaryResponse,
    CpkServerHttpProcessBoundary,
    CpkServerMcpProcessBoundary,
    CpkServerServiceRequest,
)
from .composition import (
    CpkServerComposition,
    CpkServerCompositionError,
    CpkServerProcessConfiguration,
    CpkServerProcessState,
    ObserverState,
    UnknownTargetError,
    create_cpk_server_composition,
)

__all__ = (
    "CpkServerApplicationBoundary",
    "CpkServerBoundaryResponse",
    "CpkServerHttpProcessBoundary",
    "CpkServerMcpProcessBoundary",
    "CpkServerServiceRequest",
    "CpkServerComposition",
    "CpkServerCompositionError",
    "CpkServerProcessConfiguration",
    "CpkServerProcessState",
    "ObserverState",
    "UnknownTargetError",
    "create_cpk_server_composition",
)
