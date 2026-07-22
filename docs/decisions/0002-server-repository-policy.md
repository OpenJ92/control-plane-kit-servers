# 0002 Server Repository Policy

Status: Accepted

Issue: #650

Decision:

Install repository-local policy before package metadata, test harnesses,
catalogue code, cpk-server implementation, or Hello transfer begins.

The policy establishes:

- one product owns one directory;
- core never imports servers;
- server products may import pinned core contracts;
- catalogue imports values, not applications or stores;
- cpk-server and Hello have different bootstrap roles;
- broad Docker cleanup is forbidden;
- no product implementation enters during #650.

Consequences:

- #651 can add package metadata and import surfaces against explicit root-import
  laws.
- #652 can add Docker-first harnesses and cleanup audits against explicit
  cleanup laws.
- #653 can add descriptor catalogue publication against explicit
  declaration-only laws.
- #813-#817 inherit cpk-server wrapper obligations without mistaking Hello for
  a substitute.

This decision records no product implementation.
