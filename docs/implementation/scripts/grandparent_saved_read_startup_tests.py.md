# Offline physical startup diagnosis

The existing source gate creates only synthetic input files and mounts them at
the consumed read-only launch's real target paths, as501:20 without capabilities.
The cached installer environment and proxy clearing are retained; networking is
disabled and only the external HTTP opener is intercepted. Actual file reads are
observed, not replaced. The production reader and original receipt stay unchanged.

The probe reports the first fixed stage/error category, synthetic/public file and
directory metadata, environment-presence flags and completed-read count. It prints
no graph, credential, exception text or unknown environment value. The baseline
hash is explicitly synthetic. A diagnosed HOLD is startup evidence, not acceptance
or a repair. Extra read-only source/fixture mounts supply test support only; the
five production input targets, identity and permissions remain exercised.
