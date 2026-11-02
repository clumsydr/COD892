#!/usr/bin/env python3
"""
dump_readable_logs.py

Reads a combined-payloads.txt (or any DIAG log payload text file)
and writes two human-readable CSV files:

  <output_prefix>_b881.csv   - one row per B881 record, with cumulative fields
                                AND per-carrier deltas (new_tx_bytes, retx_bytes,
                                num_mcs, num_prb, num_new_tb, num_retx_tb,
                                avg_mcs, avg_prb, retx_rate_pct, interval_sec, throughput_mbps)

  <output_prefix>_b887.csv   - one row per B887 grant, with human-readable time,
                                frame, slot, pci, nr_arfcn, tb_size, mcs, num_rbs,
                                harq_id, k1, rv, num_layers, scs

  <output_prefix>_b139.csv   - one row per B139 LTE PUSCH Tx record, with timing,
                                serving_cell_id, tb_size, num_rb, modulation, coding_rate,
                                tx_power_dbm, retx_index, rv, and UCI fields

  <output_prefix>_b173.csv   - one row per B173 LTE PDSCH Stat transport block, with
                                frame, subframe, num_layers, tb_size, mcs, modulation,
                                tb_rbs, harq_id, rv, ndi, crc_status, and rnti_type

Usage:
    python3 dump_readable_logs.py <combined_payload.txt> [output_prefix]

If output_prefix is omitted, it defaults to the payload filename without extension.

This script independently decodes and calculates all metrics:
  - Standalone multi-version B881, B887, B139, and B173 decoding (standard library only; no external dependencies).
  - B881 cumulative counters and deltas are tracked independently per component carrier (CA).
  - Throughput (Mbps) is calculated using true elapsed time intervals (dt).
  - Reset and anomaly guards handle capture gaps, clock jumps, and counter wraps.
  - Header-only CSVs are guaranteed if a log type has zero records in the input file.
"""

import sys
import os
import re
import csv
import datetime
import traceback

B881_HEADER = [
    "timestamp_epoch", "timestamp_utc",
    "cum_new_tx_bytes", "cum_retx_bytes", "cum_num_mcs", "cum_num_prb",
    "cum_num_new_tb", "cum_num_retx_tb",
    "delta_new_tx_bytes", "delta_retx_bytes", "delta_num_mcs", "delta_num_prb",
    "delta_num_new_tb", "delta_num_retx_tb",
    "avg_mcs_this_interval", "avg_prb_this_interval", "retx_rate_pct_this_interval",
    "interval_sec", "throughput_mbps",
]

B887_HEADER = [
    "timestamp_epoch", "timestamp_utc", "frame", "slot", "pci",
    "nr_arfcn", "tb_size_bytes", "mcs", "num_rbs", "harq_id", "k1",
    "rv", "num_layers", "scs",
]

B139_HEADER = [
    "timestamp_epoch", "timestamp_utc", "serving_cell_id",
    "dispatch_sfn", "dispatch_subfn", "current_sfn", "current_subfn",
    "retx_index", "is_retx", "rv", "tb_size_bytes", "tb_size_bits",
    "num_rb", "start_rb_slot0", "start_rb_slot1", "resource_alloc_type",
    "coding_rate", "mod_order", "modulation", "tx_power_dbm", "digital_gain_db",
    "ack_present", "cqi_present", "ri_present", "freq_hopping", "mirror_hopping",
    "ue_srs", "srs_occasion", "num_ack_bits", "rate_matched_ack_bits", "ack_payload",
    "num_ri_bits", "rate_matched_ri_bits", "ri_payload",
    "num_cqi_bits", "rate_matched_cqi_bits", "num_dl_carriers", "drop_pusch",
    "cyclic_shift_dmrs_slot0", "cyclic_shift_dmrs_slot1",
    "start_rb_cluster1", "num_rb_cluster1",
]

B173_HEADER = [
    "timestamp_epoch", "timestamp_utc", "frame", "subframe",
    "num_rbs_subframe", "num_layers", "num_tbs_present", "hsic_enabled",
    "tb_idx", "harq_id", "rv", "ndi", "crc_pass", "crc_status",
    "rnti_type_id", "rnti_type", "tb_size_bytes", "tb_size_bits",
    "mcs", "modulation", "tb_rbs", "did_recombining", "pmch_id", "area_id",
]

SCS_MAP = {0: "15kHz", 1: "30kHz", 2: "60kHz", 3: "120kHz"}

B139_MODULATION_MAP = {
    0: "BPSK",
    1: "QPSK",
    2: "16-QAM",
    3: "64-QAM",
    4: "256-QAM",
}

B173_RNTI_TYPE_MAP = {
    0: "C-RNTI",
    1: "RA-RNTI",
    2: "P-RNTI",
    3: "SI-RNTI",
    4: "SPS / Temp C-RNTI",
    5: "M-RNTI",
}

B173_MODULATION_MAP = {
    2: "QPSK",
    4: "16QAM",
    6: "64QAM",
    8: "256QAM",
    0: "QPSK",
    1: "16QAM",
    3: "256QAM",
}


def u16(b, o):
    return b[o] | (b[o + 1] << 8)


def u32(b, o):
    return int.from_bytes(b[o : o + 4], byteorder="little")


def u64(b, o):
    return int.from_bytes(b[o : o + 8], byteorder="little")


CDMA_EPOCH_UNIX = 315964800.0   # 1980-01-06 00:00:00 UTC
MIN_VALID_EPOCH = 946684800.0   # 2000-01-01 00:00:00 UTC
MAX_VALID_EPOCH = 2524608000.0  # 2050-01-01 00:00:00 UTC


def is_valid_diag_header(raw, i, pkt_len):
    """
    Verifies that offset `i` is preceded by the 4-byte DIAG_LOG_F outer header
    (0x10 0x00 <outer_len_u16> where outer_len == pkt_len), or starts at byte 0.
    Prevents false-positive log code matches inside other packets' timestamps/payloads.
    """
    if i >= 4:
        return raw[i - 4] == 0x10 and raw[i - 3] == 0x00 and u16(raw, i - 2) == pkt_len
    return i == 0


def parse_qxdm_time(ts_bytes):
    """
    Converts 8-byte QXDM hardware timestamp into UNIX epoch float.
    Upper 48 bits = 1.25 ms ticks since CDMA epoch (Jan 6, 1980 00:00:00 UTC).
    Lower 16 bits = fractional component (1/65536 of a tick).
    Returns None if timestamp is outside valid range [2000-01-01, 2050-01-01].
    """
    if len(ts_bytes) < 8:
        return None
    ts_int = int.from_bytes(ts_bytes, byteorder="little")
    integer_ticks = ts_int >> 16
    fractional_ticks = (ts_int & 0xFFFF) / 65536.0
    time_seconds = (integer_ticks + fractional_ticks) * 1.25 / 1000.0
    epoch_ts = CDMA_EPOCH_UNIX + time_seconds
    if not (MIN_VALID_EPOCH <= epoch_ts <= MAX_VALID_EPOCH):
        return None
    return epoch_ts


def human_time(epoch_ts):
    """Formats UNIX epoch float into human-readable UTC timestamp string."""
    return datetime.datetime.fromtimestamp(epoch_ts, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3] + " UTC"


def read_payload_bytes(payload_file):
    """Extracts raw binary payload from whitespace-separated hex tokens in payload_file."""
    with open(payload_file, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    tokens = re.findall(r"[0-9A-Fa-f]{2}", text)
    if not tokens:
        return b""
    return bytes(int(t, 16) for t in tokens)


# -----------------------------------------------------------------------------
# B887 (NR5G MAC PDSCH Status) Parser — Version 3.6
# -----------------------------------------------------------------------------
def _extract_b887_pdsch_entry(pdsch_info):
    """
    Extracts grant fields from a single `PDSCH Status Info` entry (version 3.6).
    """
    val = int.from_bytes(pdsch_info[:18], byteorder="little")
    carrier_id = (val >> 4) & 0xF
    pci = (val >> 32) & 0x3FF
    nr_arfcn = (val >> 42) & 0x3FFFFF
    tb_size = (val >> 69) & 0x3FFFF
    mcs = (val >> 90) & 0x1F
    num_rbs = (val >> 96) & 0x1FF
    rv = (val >> 105) & 0x3
    harq_id = (val >> 107) & 0xF
    k1 = (val >> 118) & 0xF
    num_layers = ((val >> 125) & 0x3) + 1

    return carrier_id, pci, nr_arfcn, tb_size, mcs, num_rbs, rv, harq_id, k1, num_layers


def parse_b887_records(raw):
    """
    Independently parses 0xB887 packets (version 3.6) from raw bytes.
    """
    records = []
    i = 0
    raw_len = len(raw)
    while i < raw_len - 3:
        if raw[i + 2] == 0x87 and raw[i + 3] == 0xB8:
            pkt_len = raw[i] | (raw[i + 1] << 8)
            if 32 <= pkt_len <= 4096 and i + pkt_len <= raw_len and is_valid_diag_header(raw, i, pkt_len):
                pkt_data = raw[i : i + pkt_len]
                pkt_time = parse_qxdm_time(pkt_data[4:12])
                if pkt_time is None:
                    i += 1
                    continue
                version_word = u32(pkt_data, 12)
                major_ver = version_word >> 16
                minor_ver = version_word & 0xFFFF

                if major_ver == 3 and minor_ver == 6:
                    rec_start = 19
                    entry_len = 24

                    if rec_start < len(pkt_data):
                        num_records = pkt_data[rec_start]
                        pos = rec_start + 1

                        for _ in range(num_records):
                            if pos + 8 > len(pkt_data):
                                break
                            slot_hdr = pkt_data[pos : pos + 8]
                            slot = slot_hdr[0]
                            mu = slot_hdr[1] & 0x0F
                            frame = u16(slot_hdr, 2) & 0x3FF
                            num_pdsch = slot_hdr[4]
                            pos += 8

                            for _ in range(num_pdsch):
                                if pos + entry_len > len(pkt_data):
                                    pos = len(pkt_data)
                                    break
                                pdsch_info = pkt_data[pos : pos + entry_len]
                                pos += entry_len

                                if len(pdsch_info) >= 18:
                                    (
                                        carrier_id,
                                        pci,
                                        nr_arfcn,
                                        tb_size,
                                        mcs,
                                        num_rbs,
                                        rv,
                                        harq_id,
                                        k1,
                                        num_layers,
                                    ) = _extract_b887_pdsch_entry(pdsch_info)

                                    records.append({
                                        "time": pkt_time,
                                        "slot": slot,
                                        "frame": frame,
                                        "scs": SCS_MAP.get(mu, f"mu{mu}"),
                                        "carrier_id": carrier_id,
                                        "pci": pci,
                                        "nr_arfcn": nr_arfcn,
                                        "tb_size": tb_size,
                                        "mcs": mcs,
                                        "num_rbs": num_rbs,
                                        "rv": rv,
                                        "harq_id": harq_id,
                                        "k1": k1,
                                        "num_layers": num_layers,
                                    })
                i += pkt_len
                continue
        i += 1
    return records


# -----------------------------------------------------------------------------
# B881 (NR5G MAC UL TB Stats) Parser — Version 3.1
# -----------------------------------------------------------------------------
def parse_b881_records(raw):
    """
    Independently parses 0xB881 packets (version 3.1) from raw bytes.
    Extracts cumulative counters per component carrier (CA).
    """
    records = []
    i = 0
    payload_idx = 0
    raw_len = len(raw)
    while i < raw_len - 3:
        if raw[i + 2] == 0x81 and raw[i + 3] == 0xB8:
            pkt_len = raw[i] | (raw[i + 1] << 8)
            if 32 <= pkt_len <= 4096 and i + pkt_len <= raw_len and is_valid_diag_header(raw, i, pkt_len):
                pkt_data = raw[i : i + pkt_len]
                pkt_time = parse_qxdm_time(pkt_data[4:12])
                if pkt_time is None:
                    i += 1
                    continue
                minor_ver = u16(pkt_data, 12)
                major_ver = u16(pkt_data, 14)

                if major_ver == 3 and minor_ver == 1:
                    num_records = pkt_data[19] if pkt_data[19] > 0 else 1
                    rec_offset_start = 24
                    rec_len = 80

                    O = rec_offset_start
                    for rec_idx in range(num_records):
                        if O + rec_len > len(pkt_data):
                            break
                        carrier_id = rec_idx
                        new_tx = u64(pkt_data, O)
                        retx = u64(pkt_data, O + 8)
                        num_mcs = u64(pkt_data, O + 16)
                        num_prb = u64(pkt_data, O + 24)
                        num_new_tb = u32(pkt_data, O + 44)
                        num_retx_tb = u32(pkt_data, O + 48)

                        records.append({
                            "time": pkt_time,
                            "payload_idx": payload_idx,
                            "carrier_id": carrier_id,
                            "new_tx": new_tx,
                            "retx": retx,
                            "num_mcs": num_mcs,
                            "num_prb": num_prb,
                            "num_new_tb": num_new_tb,
                            "num_retx_tb": num_retx_tb,
                        })
                        O += rec_len

                    payload_idx += 1
                i += pkt_len
                continue
        i += 1
    return records


# -----------------------------------------------------------------------------
# B139 (LTE PHY PUSCH Tx Report) Parser — Version 162
# -----------------------------------------------------------------------------
def parse_b139_records(raw):
    """
    Independently parses 0xB139 (LTE PHY PUSCH Tx Report, version 162) packets from raw bytes.
    """
    records = []
    i = 0
    raw_len = len(raw)
    while i < raw_len - 3:
        if raw[i + 2] == 0x39 and raw[i + 3] == 0xB1:
            pkt_len = raw[i] | (raw[i + 1] << 8)
            if 20 <= pkt_len <= 4096 and i + pkt_len <= raw_len and is_valid_diag_header(raw, i, pkt_len):
                pkt_data = raw[i : i + pkt_len]
                pkt_time = parse_qxdm_time(pkt_data[4:12])
                if pkt_time is None:
                    i += 1
                    continue
                payload = pkt_data[12:]
                if len(payload) >= 8:
                    version = payload[0]
                    if version == 162:
                        sc_raw = u16(payload, 1)
                        serving_cell_id = sc_raw & 511
                        num_records = (sc_raw >> 9) & 31
                        disp_raw = u16(payload, 4)
                        dispatch_sfn = disp_raw // 10
                        dispatch_subfn = disp_raw % 10

                        rec_size = 100
                        header_offset = 8
                        if 0 < num_records and header_offset + num_records * rec_size <= len(payload):
                            for r_idx in range(num_records):
                                rec_start = header_offset + (r_idx * rec_size)
                                rec = payload[rec_start : rec_start + rec_size]

                                sfn_sf = u16(rec, 0)
                                current_sfn = sfn_sf // 10
                                current_subfn = sfn_sf % 10

                                u2 = u16(rec, 2)
                                ack_present = (u2 >> 2) & 1
                                cqi_present = (u2 >> 3) & 1
                                ri_present = (u2 >> 4) & 1
                                freq_hopping = (u2 >> 5) & 3
                                retx_index = (u2 >> 7) & 31
                                rv = (u2 >> 12) & 3
                                mirror_hopping = (u2 >> 14) & 3

                                u4 = u32(rec, 4)
                                resource_alloc_type = u4 & 1
                                start_rb_slot0 = (u4 >> 1) & 127
                                start_rb_slot1 = (u4 >> 8) & 127
                                num_rb = (u4 >> 15) & 127

                                tb_size_bytes = u16(rec, 8)
                                coding_rate = round(u16(rec, 10) / 1024.0, 4)

                                u12 = u32(rec, 12)
                                rate_matched_ack_bits = u12 & 16383
                                ri_payload_int = (u12 >> 14) & 16383
                                ri_payload = f"0x{ri_payload_int:04x}"
                                num_ri_bits = (u12 >> 28) & 15

                                ack_payload = rec[16:32].hex()
                                rate_matched_ri_bits = (u32(rec, 32) >> 14) & 0x7FF

                                u36 = u32(rec, 36)
                                ue_srs = u36 & 1
                                srs_occasion = (u36 >> 1) & 1
                                mod_order = (u36 >> 2) & 7
                                digital_gain_db = (u36 >> 5) & 255
                                start_rb_cluster1 = (u36 >> 13) & 127
                                num_rb_cluster1 = (u36 >> 20) & 127

                                u40 = u32(rec, 40)
                                tx_power_dbm = u40 & 127
                                num_cqi_bits = (u40 >> 7) & 255
                                rate_matched_cqi_bits = (u40 >> 18) & 16383

                                u44 = u32(rec, 44)
                                num_dl_carriers = u44 & 3
                                drop_pusch = (u44 >> 16) & 1

                                u96 = u32(rec, 96)
                                cyclic_shift_dmrs_slot0 = u96 & 15
                                cyclic_shift_dmrs_slot1 = (u96 >> 4) & 15
                                num_ack_bits = 0

                                mod_str = B139_MODULATION_MAP.get(mod_order, f"Mod_{mod_order}")
                                tb_size_bits = tb_size_bytes * 8
                                is_retx = 1 if retx_index > 0 else 0

                                records.append({
                                    "time": pkt_time,
                                    "serving_cell_id": serving_cell_id,
                                    "dispatch_sfn": dispatch_sfn,
                                    "dispatch_subfn": dispatch_subfn,
                                    "current_sfn": current_sfn,
                                    "current_subfn": current_subfn,
                                    "retx_index": retx_index,
                                    "is_retx": is_retx,
                                    "rv": rv,
                                    "tb_size_bytes": tb_size_bytes,
                                    "tb_size_bits": tb_size_bits,
                                    "num_rb": num_rb,
                                    "start_rb_slot0": start_rb_slot0,
                                    "start_rb_slot1": start_rb_slot1,
                                    "resource_alloc_type": resource_alloc_type,
                                    "coding_rate": coding_rate,
                                    "mod_order": mod_order,
                                    "modulation": mod_str,
                                    "tx_power_dbm": tx_power_dbm,
                                    "digital_gain_db": digital_gain_db,
                                    "ack_present": ack_present,
                                    "cqi_present": cqi_present,
                                    "ri_present": ri_present,
                                    "freq_hopping": freq_hopping,
                                    "mirror_hopping": mirror_hopping,
                                    "ue_srs": ue_srs,
                                    "srs_occasion": srs_occasion,
                                    "num_ack_bits": num_ack_bits,
                                    "rate_matched_ack_bits": rate_matched_ack_bits,
                                    "ack_payload": ack_payload,
                                    "num_ri_bits": num_ri_bits,
                                    "rate_matched_ri_bits": rate_matched_ri_bits,
                                    "ri_payload": ri_payload,
                                    "num_cqi_bits": num_cqi_bits,
                                    "rate_matched_cqi_bits": rate_matched_cqi_bits,
                                    "num_dl_carriers": num_dl_carriers,
                                    "drop_pusch": drop_pusch,
                                    "cyclic_shift_dmrs_slot0": cyclic_shift_dmrs_slot0,
                                    "cyclic_shift_dmrs_slot1": cyclic_shift_dmrs_slot1,
                                    "start_rb_cluster1": start_rb_cluster1,
                                    "num_rb_cluster1": num_rb_cluster1,
                                })
                        i += pkt_len
                        continue
        i += 1
    return records


# -----------------------------------------------------------------------------
# B173 (LTE ML1 PDSCH Stat Indication) Parser — Version 48
# -----------------------------------------------------------------------------
def parse_b173_records(raw):
    """
    Independently parses 0xB173 (LTE ML1 PDSCH Stat Indication, version 48) packets from raw bytes.
    """
    records = []
    i = 0
    raw_len = len(raw)
    while i < raw_len - 3:
        if raw[i + 2] == 0x73 and raw[i + 3] == 0xB1:
            pkt_len = raw[i] | (raw[i + 1] << 8)
            if 16 <= pkt_len <= 4096 and i + pkt_len <= raw_len and is_valid_diag_header(raw, i, pkt_len):
                pkt_data = raw[i : i + pkt_len]
                pkt_time = parse_qxdm_time(pkt_data[4:12])
                if pkt_time is None:
                    i += 1
                    continue
                payload = pkt_data[12:]
                if len(payload) >= 4:
                    version = payload[0]
                    if version == 48:
                        num_records = payload[1]
                        rec_size = 40
                        p1_size = 12
                        tb_size = 12

                        header_offset = 4
                        if 0 < num_records and header_offset + num_records * rec_size <= len(payload):
                            for r_idx in range(num_records):
                                rec_start = header_offset + (r_idx * rec_size)
                                rec = payload[rec_start : rec_start + rec_size]

                                subfn_raw = u16(rec, 0)
                                subframe = subfn_raw & 0xF
                                frame = (subfn_raw >> 4) & 0xFFF
                                num_rbs_subframe = rec[2]
                                num_layers = rec[3]
                                num_tbs_present = rec[4]
                                cell_raw = rec[5]
                                hsic_enabled = (cell_raw >> 3) & 0xF

                                pmch_id = rec[36]
                                area_id = rec[37]

                                actual_tb_count = min(num_tbs_present, 2)
                                for tb_i in range(actual_tb_count):
                                    tb_offset = p1_size + (tb_i * tb_size)
                                    tb_bytes = rec[tb_offset : tb_offset + tb_size]

                                    harq_byte = tb_bytes[0]
                                    harq_id = harq_byte & 0xF
                                    rv = (harq_byte >> 4) & 0x3
                                    ndi = (harq_byte >> 6) & 0x1
                                    crc_pass = (harq_byte >> 7) & 0x1
                                    crc_str = "PASS" if crc_pass else "FAIL"

                                    rnti_word = u16(tb_bytes, 1)
                                    rnti_type_id = rnti_word & 0xF
                                    did_recombining = (rnti_word >> 10) & 0x1
                                    tb_size_bytes = u16(tb_bytes, 4)
                                    mcs = tb_bytes[6]
                                    tb_rbs = tb_bytes[7]
                                    mod_val = tb_bytes[8]

                                    mod_str = B173_MODULATION_MAP.get(mod_val, f"Mod_{mod_val}")
                                    rnti_str = B173_RNTI_TYPE_MAP.get(rnti_type_id, f"RNTI_{rnti_type_id}")
                                    tb_size_bits = tb_size_bytes * 8

                                    records.append({
                                        "time": pkt_time,
                                        "frame": frame,
                                        "subframe": subframe,
                                        "num_rbs_subframe": num_rbs_subframe,
                                        "num_layers": num_layers,
                                        "num_tbs_present": num_tbs_present,
                                        "hsic_enabled": hsic_enabled,
                                        "tb_idx": tb_i,
                                        "harq_id": harq_id,
                                        "rv": rv,
                                        "ndi": ndi,
                                        "crc_pass": crc_pass,
                                        "crc_status": crc_str,
                                        "rnti_type_id": rnti_word & 0xF,
                                        "rnti_type": rnti_str,
                                        "tb_size_bytes": tb_size_bytes,
                                        "tb_size_bits": tb_size_bits,
                                        "mcs": mcs,
                                        "modulation": mod_str,
                                        "tb_rbs": tb_rbs,
                                        "did_recombining": did_recombining,
                                        "pmch_id": pmch_id,
                                        "area_id": area_id,
                                    })
                        i += pkt_len
                        continue
        i += 1
    return records


# -----------------------------------------------------------------------------
# Dump CSV Functions
# -----------------------------------------------------------------------------
def dump_b887(raw_bytes, out_csv):
    """
    Decodes and writes B887 grants into out_csv sorted chronologically.
    Always writes a valid CSV (header-only if no records exist).
    """
    records = parse_b887_records(raw_bytes)
    records.sort(key=lambda r: (r["time"], r.get("frame", 0), r.get("slot", 0)))

    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(B887_HEADER)
        for r in records:
            writer.writerow([
                f"{r['time']:.6f}",
                human_time(r["time"]),
                r["frame"],
                r["slot"],
                r["pci"],
                r["nr_arfcn"],
                r["tb_size"],
                r["mcs"],
                r["num_rbs"],
                r["harq_id"],
                r["k1"],
                r.get("rv", ""),
                r.get("num_layers", ""),
                r.get("scs", ""),
            ])

    if records:
        print(f"  [B887] Wrote {len(records)} rows -> {out_csv}")
    else:
        print(f"  [B887] No records found (header-only CSV written: {out_csv})")
    return len(records)


def dump_b881(raw_bytes, out_csv):
    """
    Decodes and writes B881 records into out_csv.
    Calculates cumulative fields, per-carrier deltas, average MCS, average PRB,
    retransmission rate, and true throughput (Mbps) independently per carrier.
    Always writes a valid CSV (header-only if no records exist).
    """
    raw_records = parse_b881_records(raw_bytes)
    raw_records.sort(key=lambda r: (r["time"], r["carrier_id"]))

    rows = []
    prev_by_carrier = {}

    for r in raw_records:
        cid = r["carrier_id"]
        is_zero_record = (
            r["new_tx"] == 0
            and r["retx"] == 0
            and r["num_mcs"] == 0
            and r["num_prb"] == 0
            and r["num_new_tb"] == 0
            and r["num_retx_tb"] == 0
        )

        if is_zero_record:
            # Uninitialized or transient zero record: output zero deltas without
            # setting/overwriting the carrier's cumulative counter baseline.
            d_new_tx = d_retx = d_mcs = d_prb = d_new_tb = d_retx_tb = 0
            avg_mcs = avg_prb = retx_rate_pct = ""
            throughput_mbps = "0.0000"
            dt_str = ""
        elif cid in prev_by_carrier:
            prev = prev_by_carrier[cid]
            dt = r["time"] - prev["time"]

            # Guard against capture gaps, concatenated logs, clock jumps, or counter wraps
            is_reset = (
                dt > 2.0
                or dt < 0
                or r.get("payload_idx", 0) < prev.get("payload_idx", 0)
                or r["new_tx"] < prev["new_tx"]
                or r["retx"] < prev["retx"]
                or r["num_mcs"] < prev["num_mcs"]
                or r["num_prb"] < prev["num_prb"]
                or r["num_new_tb"] < prev["num_new_tb"]
                or r["num_retx_tb"] < prev["num_retx_tb"]
            )

            if not is_reset:
                d_new_tx = r["new_tx"] - prev["new_tx"]
                d_retx = r["retx"] - prev["retx"]
                d_mcs = r["num_mcs"] - prev["num_mcs"]
                d_prb = r["num_prb"] - prev["num_prb"]
                d_new_tb = r["num_new_tb"] - prev["num_new_tb"]
                d_retx_tb = r["num_retx_tb"] - prev["num_retx_tb"]
                total_tb = d_new_tb + d_retx_tb

                # Guard against unflagged counter discontinuities exceeding 5G NR physical limits (273 PRBs/TB)
                if (total_tb == 0 and d_prb > 0) or (total_tb > 0 and (d_prb / total_tb) > 273.0):
                    is_reset = True

            if not is_reset:
                avg_mcs = f"{(d_mcs / total_tb):.2f}" if total_tb > 0 else ""
                avg_prb = f"{(d_prb / total_tb):.2f}" if total_tb > 0 else ""
                retx_rate_pct = f"{(d_retx_tb / total_tb * 100.0):.2f}" if total_tb > 0 else ""
                throughput_mbps = (
                    f"{((d_new_tx * 8.0) / (dt * 1e6)):.4f}" if (dt > 0 and d_new_tx > 0) else "0.0000"
                )
                dt_str = f"{dt:.6f}"
            else:
                d_new_tx = d_retx = d_mcs = d_prb = d_new_tb = d_retx_tb = 0
                avg_mcs = avg_prb = retx_rate_pct = ""
                throughput_mbps = "0.0000"
                dt_str = ""
            prev_by_carrier[cid] = r
        else:
            # Baseline first non-zero record for this component carrier
            d_new_tx = d_retx = d_mcs = d_prb = d_new_tb = d_retx_tb = 0
            avg_mcs = avg_prb = retx_rate_pct = ""
            throughput_mbps = "0.0000"
            dt_str = ""
            prev_by_carrier[cid] = r

        rows.append([
            f"{r['time']:.6f}",
            human_time(r["time"]),
            r["new_tx"],
            r["retx"],
            r["num_mcs"],
            r["num_prb"],
            r["num_new_tb"],
            r["num_retx_tb"],
            d_new_tx,
            d_retx,
            d_mcs,
            d_prb,
            d_new_tb,
            d_retx_tb,
            avg_mcs,
            avg_prb,
            retx_rate_pct,
            dt_str,
            throughput_mbps,
        ])

    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(B881_HEADER)
        writer.writerows(rows)

    if rows:
        print(f"  [B881] Wrote {len(rows)} rows -> {out_csv}")
    else:
        print(f"  [B881] No records found (header-only CSV written: {out_csv})")
    return len(rows)


def dump_b139(raw_bytes, out_csv):
    """
    Decodes and writes B139 LTE PUSCH Tx records into out_csv sorted chronologically.
    Always writes a valid CSV (header-only if no records exist).
    """
    records = parse_b139_records(raw_bytes)
    records.sort(key=lambda r: (r["time"], r.get("current_sfn", 0), r.get("current_subfn", 0)))

    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(B139_HEADER)
        for r in records:
            writer.writerow([
                f"{r['time']:.6f}",
                human_time(r["time"]),
                r["serving_cell_id"],
                r["dispatch_sfn"],
                r["dispatch_subfn"],
                r["current_sfn"],
                r["current_subfn"],
                r["retx_index"],
                r["is_retx"],
                r["rv"],
                r["tb_size_bytes"],
                r["tb_size_bits"],
                r["num_rb"],
                r["start_rb_slot0"],
                r["start_rb_slot1"],
                r["resource_alloc_type"],
                r["coding_rate"],
                r["mod_order"],
                r["modulation"],
                r["tx_power_dbm"],
                r["digital_gain_db"],
                r["ack_present"],
                r["cqi_present"],
                r["ri_present"],
                r["freq_hopping"],
                r["mirror_hopping"],
                r["ue_srs"],
                r["srs_occasion"],
                r["num_ack_bits"],
                r["rate_matched_ack_bits"],
                r["ack_payload"],
                r["num_ri_bits"],
                r["rate_matched_ri_bits"],
                r["ri_payload"],
                r["num_cqi_bits"],
                r["rate_matched_cqi_bits"],
                r["num_dl_carriers"],
                r["drop_pusch"],
                r["cyclic_shift_dmrs_slot0"],
                r["cyclic_shift_dmrs_slot1"],
                r["start_rb_cluster1"],
                r["num_rb_cluster1"],
            ])

    if records:
        print(f"  [B139] Wrote {len(records)} rows -> {out_csv}")
    else:
        print(f"  [B139] No records found (header-only CSV written: {out_csv})")
    return len(records)


def dump_b173(raw_bytes, out_csv):
    """
    Decodes and writes B173 LTE PDSCH Stat records into out_csv sorted chronologically.
    Always writes a valid CSV (header-only if no records exist).
    """
    records = parse_b173_records(raw_bytes)
    records.sort(key=lambda r: (r["time"], r.get("frame", 0), r.get("subframe", 0), r.get("tb_idx", 0)))

    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(B173_HEADER)
        for r in records:
            writer.writerow([
                f"{r['time']:.6f}",
                human_time(r["time"]),
                r["frame"],
                r["subframe"],
                r["num_rbs_subframe"],
                r["num_layers"],
                r["num_tbs_present"],
                r["hsic_enabled"],
                r["tb_idx"],
                r["harq_id"],
                r["rv"],
                r["ndi"],
                r["crc_pass"],
                r["crc_status"],
                r["rnti_type_id"],
                r["rnti_type"],
                r["tb_size_bytes"],
                r["tb_size_bits"],
                r["mcs"],
                r["modulation"],
                r["tb_rbs"],
                r["did_recombining"],
                r["pmch_id"],
                r["area_id"],
            ])

    if records:
        print(f"  [B173] Wrote {len(records)} rows -> {out_csv}")
    else:
        print(f"  [B173] No records found (header-only CSV written: {out_csv})")
    return len(records)


# -----------------------------------------------------------------------------
# Main CLI Entry Point
# -----------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python3 dump_readable_logs.py <combined_payload.txt> [output_prefix]")
        sys.exit(1 if len(sys.argv) < 2 else 0)

    payload_file = sys.argv[1]
    if not os.path.isfile(payload_file):
        print(f"ERROR: payload file not found: {payload_file}")
        sys.exit(1)

    out_prefix = sys.argv[2] if len(sys.argv) >= 3 else os.path.splitext(payload_file)[0]
    out_dir = os.path.dirname(out_prefix)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"Processing: {payload_file}")
    raw_bytes = read_payload_bytes(payload_file)
    if not raw_bytes:
        print(f"WARNING: No hex data extracted from {payload_file}")

    failed = False
    try:
        dump_b881(raw_bytes, f"{out_prefix}_b881.csv")
    except Exception:
        failed = True
        print("  [B881] ERROR while dumping B881 CSV:")
        traceback.print_exc()

    try:
        dump_b887(raw_bytes, f"{out_prefix}_b887.csv")
    except Exception:
        failed = True
        print("  [B887] ERROR while dumping B887 CSV:")
        traceback.print_exc()

    try:
        dump_b139(raw_bytes, f"{out_prefix}_b139.csv")
    except Exception:
        failed = True
        print("  [B139] ERROR while dumping B139 CSV:")
        traceback.print_exc()

    try:
        dump_b173(raw_bytes, f"{out_prefix}_b173.csv")
    except Exception:
        failed = True
        print("  [B173] ERROR while dumping B173 CSV:")
        traceback.print_exc()

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
