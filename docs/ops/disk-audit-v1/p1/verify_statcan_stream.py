#!/usr/bin/env python3
"""Stream-verify expanded StatCan CSVs against their source ZIPs.

Gate-2 evidence for disk-recovery P1. For each sc_*.zip:
  1. zip integrity: zipfile.testzip-style CRC check while streaming member
  2. content equality: sha256 + crc32 of decompressed member stream
     compared byte-for-byte against the on-disk CSV (streaming, no copy)
Writes nothing to the scanned dirs. Emits JSON evidence.
"""
import hashlib, json, sys, zipfile, zlib
from pathlib import Path

STATCAN = Path.home() / "northshore_property_watchdog/data/research/macro/raw/statcan"
CHUNK = 1 << 22  # 4MiB


def hash_stream(fh):
    sha, crc, n = hashlib.sha256(), 0, 0
    while True:
        b = fh.read(CHUNK)
        if not b:
            break
        sha.update(b); crc = zlib.crc32(b, crc); n += len(b)
    return sha.hexdigest(), crc & 0xFFFFFFFF, n


def verify(zip_path: Path, member: str, disk_path: Path):
    rec = {"zip": str(zip_path), "member": member, "csv": str(disk_path)}
    with zipfile.ZipFile(zip_path) as zf:
        info = zf.getinfo(member)
        rec["zip_declared_size"] = info.file_size
        rec["zip_declared_crc32"] = f"{info.CRC:08x}"
        rec["zip_compress_size"] = info.compress_size
        with zf.open(member) as fh:
            sha, crc, n = hash_stream(fh)
        rec["zip_member_sha256"] = sha
        rec["zip_member_crc32"] = f"{crc:08x}"
        rec["zip_member_size"] = n
        rec["zip_crc_ok"] = (crc == info.CRC) and (n == info.file_size)
    with disk_path.open("rb") as fh:
        sha, crc, n = hash_stream(fh)
    rec["disk_sha256"] = sha
    rec["disk_crc32"] = f"{crc:08x}"
    rec["disk_size"] = n
    rec["content_equal"] = (
        rec["zip_member_sha256"] == rec["disk_sha256"]
        and rec["zip_member_crc32"] == rec["disk_crc32"]
        and rec["zip_member_size"] == rec["disk_size"]
    )
    rec["verdict"] = "PASS" if (rec["zip_crc_ok"] and rec["content_equal"]) else "FAIL"
    return rec


def main():
    out = []
    for zp in sorted(STATCAN.glob("sc_*.zip")):
        with zipfile.ZipFile(zp) as zf:
            names = [n for n in zf.namelist() if n.endswith(".csv") and "_MetaData" not in n]
        for member in names:
            disk = zp.parent / zp.stem / member
            if not disk.exists():
                out.append({"zip": str(zp), "member": member,
                            "verdict": "MISSING_ON_DISK", "csv": str(disk)})
                continue
            print(f"verifying {zp.name}:{member} -> {disk.name} ...", flush=True)
            out.append(verify(zp, member, disk))
            print(f"  -> {out[-1]['verdict']}", flush=True)
    print(json.dumps(out, indent=2))
    ok = all(r["verdict"] == "PASS" for r in out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
