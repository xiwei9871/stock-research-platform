# System Permission Gaps — 2026-10-27 disk audit

These paths could NOT be measured without elevated privileges / Full Disk
Access. They are listed so the unexplained ~60-70GB on the Data volume is
honestly attributed as UNKNOWN, not assumed.

| Path | Read error | Likely content | How to measure |
|---|---|---|---|
| `/System/Volumes/Data/.Spotlight-V100` | `drwx--x--- root:_mds_stores` — du returns 0 | Spotlight index; was rebuilding this morning (mds at 22% CPU) after the panic | `sudo du -sh /System/Volumes/Data/.Spotlight-V100` |
| `/System/Volumes/Data/.fseventsd` | `drwx------ root` | fsevents journal — user measured 884KB via partial read; actual total unreadable | `sudo du -sh` |
| `/System/Volumes/Data/.DocumentRevisions-V100` | `d--x--x--x root` | per-file version store | `sudo du -sh` |
| `/private/var/db/*` subdirs (diagnostics, dyld, systemstats) | root-owned | diagnostics collections, spin dumps, powerlogs | `sudo du -xsh /private/var/db/*` |
| `/private/var/folders/*/*/0` system-owned subtrees | per-user ownership | temp files for root daemons | `sudo du -xsh /private/var/folders` |
| `/Library/` root-only subtrees | mixed | system caches, CoreSimulator, fonts | `sudo du -xsh /Library/*` |

## Recommended single command for owner

```bash
sudo du -xsh /System/Volumes/Data/{,.}* 2>/dev/null | sort -rh | head -25
```

`-x` stays on the Data filesystem; the dot-entries expose Spotlight /
fseventsd / DocumentRevisions directly.

## Notes

- `lsof +L1` (unprivileged) shows no deleted-but-open files >100MB for the
  current boot — the pre-panic handles were released by the reboot.
- No APFS local snapshots exist on / or Data.
- No SIP/security changes were made or are recommended; these gaps stay gaps
  until the owner runs the sudo command above.
