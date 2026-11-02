#!/usr/bin/env python3
"""
Convert pcap / pcapng captures to CSV, one row per IP packet:

  timestamp  - capture time, epoch seconds (float, microsecond precision)
  length     - packet length in bytes as seen on the wire
  src_ip     - source IP (IPv4 or IPv6)
  dst_ip     - destination IP
  direction  - "downlink" (to the device), "uplink" (from the device), "other" (neither)

Input : <IN_ROOT>/<operator>/<location>/<date>/capture_*/<name>.pcap
Output: <OUT_ROOT>/<operator>/<location>/<date>/capture_*/<name><OUT_SUFFIX>.csv
e.g.  data/Airtel/indoor_Bharti501/20261006/capture_000_20261006_162251/capture_20261006_162251.pcap
  ->  results/Throughput/Airtel/indoor_Bharti501/20261006/capture_000_20261006_162251/capture_20261006_162251.csv

The device IP is DEVICE_IP if set; otherwise it is detected per file as the IP that
appears in the most packets (the phone is on one end of nearly every packet).
Non-IP packets (ARP etc.) are skipped and counted in the log.

Usage:
  python pcap_to_csv.py                      # operators / locations / dates from CONFIG
  python pcap_to_csv.py a.pcap b.pcapng      # just these files; CSV written next to each one
"""
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scapy.all import PcapReader, IP, IPv6

# ───────────────────────────── CONFIG ──────────────────────────────
IN_ROOT = Path("data")
OUT_ROOT = Path("results/Throughput")

OPERATORS = ["Airtel", "Jio", "Vodafone"]          # None = every operator folder in IN_ROOT; or e.g. ["Airtel", "Jio"]
LOCATIONS = ["indoor_Shubham_JiaSarai"]

START_DATE, END_DATE = date(2026, 10, 18), date(2026, 10, 18)   # both inclusive
DATES = [(START_DATE + timedelta(days=i)).strftime("%Y%m%d")
         for i in range((END_DATE - START_DATE).days + 1)]

PATTERNS = ["*.pcap", "*.pcapng"]
OUT_SUFFIX = ""           # added to the CSV name, e.g. "_packets" -> capture_..._packets.csv
DEVICE_IP = None          # e.g. "10.45.0.2"; None = auto-detect per file
OVERWRITE = False         # False: skip pcaps whose CSV already exists
# ───────────────────────────────────────────────────────────────────


def log(msg):
    print(msg, flush=True)

def ci_child(parent, name):
    """Case-insensitive child lookup; returns None if parent is None / missing."""
    if parent is None or not parent.is_dir():
        return None
    p = parent / name
    if p.exists():
        return p
    for c in parent.iterdir():
        if c.name.lower() == name.lower():
            return c
    return None

def read_pcap(path):
    """Stream the capture packet by packet (does not load the whole file into memory)."""
    rows, skipped = [], 0
    with PcapReader(str(path)) as reader:
        for pkt in reader:
            if IP in pkt:
                layer = pkt[IP]
            elif IPv6 in pkt:
                layer = pkt[IPv6]
            else:
                skipped += 1
                continue
            # wirelen = original length even if the capture was truncated (snaplen)
            length = getattr(pkt, "wirelen", None) or len(pkt)
            rows.append((float(pkt.time), int(length), layer.src, layer.dst))
    df = pd.DataFrame(rows, columns=["timestamp", "length", "src_ip", "dst_ip"])
    return df, skipped


def add_direction(df, device_ip=None):
    if df.empty:
        df["direction"] = pd.Series(dtype=object)
        return df, device_ip
    if device_ip is None:
        device_ip = pd.concat([df["src_ip"], df["dst_ip"]]).value_counts().idxmax()
    df["direction"] = np.select(
        [df["dst_ip"] == device_ip, df["src_ip"] == device_ip],
        ["downlink", "uplink"],
        default="other",
    )
    return df, device_ip


def convert(pcap, dest):
    log(f"\n[{pcap}]")
    df, skipped = read_pcap(pcap)
    df, dev = add_direction(df, DEVICE_IP)
    df = df.sort_values("timestamp", kind="stable")

    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dest, index=False)

    counts = df["direction"].value_counts().to_dict()
    log(f"    {len(df)} IP packets ({skipped} non-IP skipped), device IP {dev}")
    log(f"    direction counts: {counts}")
    if counts.get("other", 0) > 0.05 * max(len(df), 1):
        log("    ! more than 5% of packets are 'other' - check the device IP (set DEVICE_IP)")
    log(f"    -> {dest}")


def out_path(pcap):
    rel = pcap.relative_to(IN_ROOT)
    return OUT_ROOT / rel.parent / f"{pcap.stem}{OUT_SUFFIX}.csv"


def collect_jobs():
    if not IN_ROOT.is_dir():
        sys.exit(f"{IN_ROOT} not found")

    if OPERATORS:
        op_dirs = []
        for op in OPERATORS:
            d = ci_child(IN_ROOT, op)
            if d is None:
                log(f"- no folder for operator {op} under {IN_ROOT}, skipping")
            else:
                op_dirs.append(d)
    else:
        op_dirs = sorted(p for p in IN_ROOT.iterdir() if p.is_dir())

    jobs = []
    for op_dir in op_dirs:
        for loc in LOCATIONS:
            loc_dir = ci_child(op_dir, loc)
            if loc_dir is None:
                log(f"- no folder {op_dir.name}/{loc}, skipping")
                continue
            for d in DATES:
                date_dir = ci_child(loc_dir, d)
                if date_dir is None:
                    continue
                for cap in sorted(p for p in date_dir.glob("capture_*") if p.is_dir()):
                    pcaps = sorted({p for pat in PATTERNS for p in cap.rglob(pat)})
                    if not pcaps:
                        log(f"- no pcap in {cap}")
                    jobs.extend((p, out_path(p)) for p in pcaps)
    return jobs


def main():
    if len(sys.argv) > 1:
        jobs = [(Path(p), Path(p).with_suffix(".csv")) for p in sys.argv[1:]]
    else:
        jobs = collect_jobs()

    if not jobs:
        sys.exit(f"No pcaps found for locations {LOCATIONS}, dates {DATES[0]}-{DATES[-1]}")
    log(f"Found {len(jobs)} capture(s)")

    ok = failed = skipped = 0
    for pcap, dest in jobs:
        if dest.exists() and not OVERWRITE:
            log(f"- {dest} already exists, skipping (set OVERWRITE = True to redo)")
            skipped += 1
            continue
        try:
            convert(pcap, dest)
            ok += 1
        except Exception:
            failed += 1
            log(f"    !! failed on {pcap}")
            traceback.print_exc()
    log(f"\nDone. {ok} converted, {skipped} already existed, {failed} failed.")


if __name__ == "__main__":
    main()