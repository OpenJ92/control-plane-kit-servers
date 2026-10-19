"""#188 coordinator interface scaffold; behavior intentionally absent for causal red."""
import fcntl
import os
import signal
import stat
import subprocess
import time

from . import managed


def run(configuration, *, token_path):
    raise NotImplementedError('managed connector lifecycle is not implemented')


def _spawn_native(token_path):
    raise NotImplementedError('managed connector launch is not implemented')


def _open_diagnostic_sink():
    raise NotImplementedError('managed connector diagnostic admission is not implemented')


def _emit_diagnostic(descriptor, reason, code=None):
    raise NotImplementedError('managed connector diagnostic emission is not implemented')


def _close_diagnostic_sink(descriptor):
    raise NotImplementedError('managed connector diagnostic closure is not implemented')
