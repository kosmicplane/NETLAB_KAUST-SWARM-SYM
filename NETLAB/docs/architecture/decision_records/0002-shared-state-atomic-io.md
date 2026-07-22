# ADR 0002: Atomic shared-state I/O

All host/container coordination JSON is written through one atomic writer with explicit mode, fsync, replace, and directory durability. This prevents unreadable root-owned heartbeat files and partial JSON.
