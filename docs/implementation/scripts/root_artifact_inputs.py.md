Source: [root_artifact_inputs.py](../../../scripts/root_artifact_inputs.py).

The bounded #191 owner validates the optional current CPK/Secrets pair. Selection
is closed to role-specific repository digests, a source commit and explicit mode.
Metadata admission separates RepoDigest from actual image ID, checks platform,
numeric user/source label and optionally rechecks a prior ID. Execution requires
actual container Image to equal the admitted ID.

Provenance compares actual selected direct_url records with the gate's generated
canonical cohort. URL/subdirectory must match; editable/VCS/local substitution
refuses. Archive metadata is allowed but not printed. CLI reads are bounded
at65536 bytes; errors omit inputs. Producer review/equivalence remains external.

The pure functions are the focused targets. CLI admit also checks the complete
environment tuple. Existing smoke owners invoke execution/provenance commands;
only validated public URL/subdirectory fields are reported. No Docker operation
or production authority belongs to this Python owner.
