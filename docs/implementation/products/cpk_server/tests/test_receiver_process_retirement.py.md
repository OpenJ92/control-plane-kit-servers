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

The corrected checkpoint `e6841fd` reached exactly the intended retained-file
failure in run `39177329237`, while the original factory identity law passed.
Independent terminal review and North's release cleared the implementation hold.
The same install/remove/install assertions remain unchanged during repair.
Additional bounded safety cases preserve an unowned file, refuse a symlinked
installed file before touching its target, and simulate a file appearing during
child stop: partial retirement stays uncertain, retains incarnation bookkeeping
and blocks reinstallation. They exercise only the process/file boundary, not
Operations state-machine behavior or recovery.

Kepler found that retaining deleted paths as cleanup authority could delete a
later foreign incarnation. Successful and partial retirement cases now create
a foreign file at a deleted path and require repeated/final close to preserve
it. Active ownership is released per successful unlink; retired-path evidence
is separate and cannot grant destructive authority. These are focused ownership
regressions, not additional control-plane state-machine tests.
