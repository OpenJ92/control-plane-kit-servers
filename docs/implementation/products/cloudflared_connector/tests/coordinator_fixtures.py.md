# Controlled coordinator effects

Source: [coordinator_fixtures.py](../../../../../products/cloudflared_connector/tests/coordinator_fixtures.py).

The #188 fixture supplies generated real Core configuration and controlled child,
group, signal, clock and host effects. It does not choose shutdown/result policy:
tests arrange external observations and assert signals, ownership and return codes
from the product callable. Host serving/shutdown use actual threads/events; a
captured real sleep yields to those threads while the controlled clock advances.
The fixture releases and joins its host threads in finally and restores patched
signal/environment/effect boundaries. No real process group is signalled.

Record the first actual requested-handler delivery for deadline assertions;
scheduled actions may be delivered later by a valid polling interval. Nondefault
prior handlers expose restoration defects. A group signal changes only a still
running leader's returncode; group cleanup cannot rewrite an already-exited leader.
Joining a controlled finished host makes competing-observation tests deterministic.
A one-shot controlled-clock hook can interrupt first-stop candidate construction;
the host refuses serving entry after close so delayed-entry regressions cannot
silently accept an impossible SDK startup sequence. Neither fixture change adds
a coordinator policy algorithm.

These controls cannot establish PID1/process exit, real native connection/drain,
kernel timing or Docker stop behavior. Those belong to the later source-image
witness. Current coordinator scaffold fails deliberately before these effects.
