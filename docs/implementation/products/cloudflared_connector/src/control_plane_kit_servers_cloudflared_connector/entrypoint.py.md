# Managed entrypoint boundary

Source: [entrypoint.py](../../../../../../products/cloudflared_connector/src/control_plane_kit_servers_cloudflared_connector/entrypoint.py).

`main() -> int` calls the common SDK configuration loader once, reads the native
token-file path binding once, validates the absolute non-NUL path and exact
managed product surface, then invokes the existing coordinator. Configuration
and binding failures return1 without exposing submitted material or exceptions.
The entrypoint does not open the token file. Module execution forwards the
coordinator result to `SystemExit`; imports do not run `main()`.

Native custody, signals, cleanup and exit mapping remain coordinator-owned.
The coordinator also retains its own validation for independent callers; this
entrypoint validates before handing control to that effect owner. There is no
restart loop, extra thread, SDK host, new signal handler or public interface.

The unchanged target checkpoint9f140e4 earned independent CAUSAL-RED PASS in
run39375332158, with14 intentional NotImplementedError records across eight
methods and inert import already green. This source replaces only that scaffold.
It has not yet earned green execution or image/PID1 acceptance; the review/run
record on #284 is authoritative. No alternate or host verification was used.
