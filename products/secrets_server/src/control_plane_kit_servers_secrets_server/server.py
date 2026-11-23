"""Import-safe product launcher joining independent public receiver metadata."""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from control_plane_kit_core.http_verification_sample_installation import HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT
from control_plane_kit_secrets import application
from control_plane_kit_secrets.bootstrap import ProviderConfigurationError
from control_plane_kit_secrets.control import read_secrets_control_configuration
from control_plane_kit_server_sdk.wrapper import load_http_verification_sample_configuration

from .configuration import HTTP_SAMPLE_SLOT, secrets_http_sample_binding


def create_app(
    *, environment: Mapping[str, str] | None = None,
    clock: Callable[[], int] | None = None,
    http_sample_clock: Callable[[], float] | None = None,
) -> object:
    """Admit public opt-in before the one Secrets private initializer."""
    source = os.environ if environment is None else environment
    try:
        companion = HTTP_VERIFICATION_SAMPLES_CONFIGURATION_ENVIRONMENT
        if ((companion in source) != (companion in os.environ)
                or source.get(companion) != os.environ.get(companion)):
            raise ValueError
        if companion in source and source[companion] != HTTP_SAMPLE_SLOT.target_path:
            raise ValueError
        control = read_secrets_control_configuration(source)
        binding = None
        if companion in source:
            configuration = load_http_verification_sample_configuration()
            binding = secrets_http_sample_binding(control, configuration)
    except Exception:
        failure = ProviderConfigurationError()
    else:
        return application.app_from_environment(
            environment, control=control, http_verification_binding=binding,
            clock=clock, http_sample_clock=http_sample_clock,
        )
    raise failure
