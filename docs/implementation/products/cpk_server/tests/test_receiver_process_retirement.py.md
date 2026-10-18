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
