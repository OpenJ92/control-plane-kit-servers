# Hosted activity public transport

The existing hosted workflow drives public CPK HTTP/MCP operations. Its MCP read
and command helpers both accept an explicit authorization value so a scenario can
retain distinct acting identities. Existing legacy callers retain their declared
default identity; the G enrollment scenario must supply identity explicitly.

HTTP requests reject redirects and responses over one MiB. HTTP failures retain
only the status when available, without response bodies or originating exception
context. MCP failure messages likewise omit server payloads. These controls keep
foreign state and credential material out of source-live reports.

Legacy workflow setup, network repair and private evidence helpers are not G
acceptance paths. G reuses the maintained public client for topology progression;
this helper does not acquire permission or implement durable state transitions.
