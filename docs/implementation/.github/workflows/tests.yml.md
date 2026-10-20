Source: [tests.yml](../../../../.github/workflows/tests.yml).

The existing authenticated host step owns exact-reference acquisition. It retains
registry allowlists, required fixed entries, optional A/B/gateway inputs, explicit
Linux/amd64 selection and RepoDigest checks. It records only whitelisted image
identity/platform/user/entrypoint/source-label/Descriptor observations in its own
temporary directory, checking the daemon is unchanged across acquisition.

#191 replaces the untyped ID equality with the actual stdlib
`qualify_preloaded_images` caller via the existing policy Python image. The
verifier receives readonly source/metadata mounts, `--network none`, no socket
and no registry credentials. Fixed optional overlaps cannot bypass linked proof;
true extras keep their prior metadata contract without invented fixed-config
qualification. The bounded report separates config and execution identities.

The temporary directory is unique to this step and removed on exit; shared images
remain retained. The next step remains the unmodified owning `./test.sh`.
No separate test runner, registry client, environment matrix, publication or
implicit runtime acceptance was added. Source review does not claim CI execution.
