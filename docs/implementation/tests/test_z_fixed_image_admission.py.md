Source: [test_z_fixed_image_admission.py](../../../tests/test_z_fixed_image_admission.py).

#191's staged early target exercises the existing `inspect_inputs` boundary with
five closed, effect-free Engine/Interpreter observations. Original manifest bytes
are independently hashed and their historical config links checked before the
call. Thus the old config-ID equality rejects genuinely linked manifest-valued
observations; an unavailable future helper is not the reason for this target red.
The owning product test path is added only during the test's import/call scope.

The absent/disagreeing Interpreter admission test lives here alongside the positive
admission law. Both negative observations retain their `ValueError` and zero-create
assertions. The existing runner starts each test root in a separate subprocess,
so importing the public witness here cannot leave a cached factory reference in
the later product suite while its bootstrap tests evict product modules. No new
runner, cache mutation, or weakened factory identity assertion is needed.

On the implemented side the same test requires a complete daemon-bound result,
unchanged config identities and explicit manifest-valued execution proofs. No
Docker client, registry, network, provider or application is executed. It belongs
to the normal root unittest discovery under Docker-backed `./test.sh`; its early
position prevents a causal-red checkpoint from proceeding into live fixtures.
No result is claimed before a released run. Later product targets may remain
unreached behind this first stop and must be reported as such.
