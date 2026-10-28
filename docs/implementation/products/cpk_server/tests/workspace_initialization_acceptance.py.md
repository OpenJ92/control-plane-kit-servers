Source: [workspace_initialization_acceptance.py](../../../../../products/cpk_server/tests/workspace_initialization_acceptance.py).

#346 adds component evidence to the existing real PostgreSQL receiver witness.
The existing disposable-schema fixture can now leave its owned namespace empty;
its default installation and exact cleanup stay unchanged. Only the connection
destination is replaced for this component fixture. Actual protected-input and
administrator admission, schema installer, initialize UoW, and read owner execute.
This is not full Docker root acquisition or #347 public enrollment evidence.

An independent connection checks committed schema before initialization opens.
Lost schema acknowledgement prevents initialization; lost final acknowledgement
leaves the actual receipt discoverable by the read-only helper. Conflict/missing
receipts remain distinct. Inspection cannot call either mutation owner, and its
result cannot overwrite the prior acquisition helper's progress. No schema or
permission state machine is reimplemented. Initial target checkpoint is unrun.
