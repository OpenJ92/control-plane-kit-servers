Source: [bootstrap_enrollment.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_enrollment.py).

#347 compares public enrollment results with the admitted private intent. Actual
Operations receipt constructors validate administration and management values.
The permission receipt has no descriptor decoder in the selected owner, so this
adapter closes its wire fields and constructs that owner value. It compares the
full actor/target, installation/workspace, explicit key, operation and prior
revision. Readback must equal the owner's resulting record; this adapter does
not calculate a grant union or mutate a store.

Management binds the actual active Docker authority registration response and
readback to its private intent before sending the grant. The resulting assignment
must name the same registration, runtime, authority and installed capability.
Fresh setup refuses replayed results and never retries a mutation. Callers retain
only bounded receipt/registration/revision/state coordinates, with private error
context removed at the public helper boundary.
