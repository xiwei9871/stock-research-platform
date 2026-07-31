# Theme Research 25-Theme Production Restore Evidence

Date: 2026-07-31 (Asia/Shanghai)

## Release and schema

- Production URL: `https://stock.manqiaotechnology.com`
- Release ID: `0ffe1e7ee01ed598dcf95f952434eadb36cfa7ae`
- External `release.json` matched the release ID.
- Schema status after migration: `current`
- Applied DDL SHA-256: `d41e9b7d5d29d5055099bae9e9c5446ab305f53731ba1626162c001c6dfcabf8`
- Missing schema objects after migration: none

## Backup

- Backup: `/home/jqz/backups/theme-research-25-restore-20260731/research-before-25-themes-v18.dump`
- Size: `22495324` bytes
- SHA-256: `59a2bf8b4dfe7ff5cfd3a53758009751780b5964f5193aacdc15e9ced306d2fc`
- `pg_restore --list` contained the Theme Research theme, node, import-run, and store-state tables and table data.

## Checkpoint and gate

- Checkpoint: `eba5cdfc700a02d961e441cc1b92824ff9e35c7e`
- Manifest SHA-256: `3fc6d67eb68b3b375b870543cb2ab20da489065d60eaa5685f8f320e5b28f34f`
- Raw checkpoint package SHA-256: `48785cbe949ee35eacae70b0f1946edc87ae372c87f78ffd8e895f448cf2713e`
- Raw checkpoint counts: 25 themes, 270 nodes, 282 sources, 320 claims, 248 company mappings.
- The raw full-package gate correctly rejected newer revisions of the two production themes.
- The additive gate preserved the current two-theme package and added only the 23 missing checkpoint themes.
- Additive gate result: allowed, 23 theme inserts, zero updates, and zero deactivations in every family.
- Guarded desired package SHA-256: `34d23959c107ad997f776aed78bbdf1d4aefb54a48104186198e0c3a1e6b1576`

## Transaction

- Starting generation: `4`
- Resulting generation: `5`
- Status: `committed`
- Idempotency key: `theme-research-25-eba5cdfc-additive-20260731`
- Change set: `change-08ee44c2-4438-483b-8566-8bc3e1983c4b`
- Import run: `import-c03c6568-b7ab-4d5e-bb6a-d442e5398c8f`
- Resulting active package counts: 25 themes, 270 nodes, 268 sources, 308 claims, and 236 company mappings. These counts intentionally retain the production versions of the original two themes rather than replacing them with their newer checkpoint revisions.
- The committed transaction returned 23 theme inserts, two unchanged themes, zero theme updates, and zero theme deactivations.
- The committed transaction's returned semantic diff contained zero updates and zero deactivations in every normalized object family.

## Existing-theme preservation

- `ai_power_value_capture_v1`: theme version `4`, row version `3`, content SHA-256 `10191dc34f0bf26daa78a3ac67ddd7933d689eead43a9028a34ba5a9c89d293f`
- `humanoid_robotics_head_to_toe_v1`: theme version `1`, row version `1`, content SHA-256 `9ba498112f302cd069d4affe1d2c27a73402685eddf47e5cd77efe675b7604ec`
- Both records matched their preflight fingerprints after the transaction.

## Read verification

- Database active-theme count: `25`
- Server-side theme list total: `25`
- `industrial_robots_value_chain_v1`: 10 nodes, 10 sources
- `new_energy_storage_value_chain_v1`: 13 nodes, 10 sources
- `semiconductor_manufacturing_equipment_value_chain_v1`: 11 nodes, 10 sources
- Authenticated external list displayed `25 个主题`.
- The new-energy-storage detail rendered its overview, 13 nodes, evidence gaps, and company mappings.
- Browser console errors on the verified detail: none.
- Production logs recorded HTTP 200 for the theme list and the new-energy-storage detail.
- Theme Research verification-window `500`, `ERROR`, or `Traceback` count: `0`.
