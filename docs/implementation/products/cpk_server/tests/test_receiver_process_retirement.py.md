Source: [test_receiver_process_retirement.py](../../../../../products/cpk_server/tests/test_receiver_process_retirement.py).

Servers #255's causal target exercises the existing process compute port's
install/remove/install sequence with real private files and a tiny child-handle
double. It requires exact installed-file and directory retirement, removal of
incarnation bookkeeping, successful fresh installation and preservation of a
foreign peer file. It does not emulate Operations or claim real process evidence;
the existing joined source-process witness owns that evidence. Before repair,
the normal gate must fail on retained installed files after successful removal,
not on missing imports or setup. Source/test release and independent plan review
are recorded on Servers #255. No provider or credential effect is introduced.

The first normal run reached that retained-file failure but also exposed an
unrelated factory-class identity assertion: importing the live composition at
discovery time retained its factory across existing import-isolation tests.
The target now imports the live owner only inside its helper/test, following
the established process-port tests. No production reload, test ordering or
factory identity assertion is changed. Corrected gate evidence is recorded on
PR #275; neither the first intended failure nor this source correction alone
proves the full suite green.
