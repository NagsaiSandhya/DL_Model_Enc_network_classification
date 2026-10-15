"""Extract windowed flow-statistics features from captures.

Reads data/processed/capture_inventory.csv, processes up to
MAX_PACKETS_PER_CAPTURE packets per capture with scapy (validating
headers before access), partitions into non-overlapping windows of
WINDOW_SIZE packets, and computes the 24 FEATURE_NAMES statistics.

Outputs:
  data/processed/features_windows.csv
  data/processed/features_sequences.npz  (for 1D-CNN)
  data/processed/feature_schema.json
  data/processed/label_mapping.json
  data/processed/extraction_log.json
"""
import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np

from common import (
    PROJECT_ROOT, PROCESSED_DIR, FEATURE_NAMES, LABEL_MAPPING,
    SEQ_LEN, MAX_PACKETS_PER_CAPTURE, WINDOW_SIZE,
    window_to_feature, window_to_sequence,
)

# CRITICAL: import scapy layers at module top, BEFORE any PcapReader is
# created. Scapy registers linktype->packet-class mappings (e.g. DLT_RAW/101
# -> IP, DLT_EN10MB/1 -> Ether) when layers are imported. Lazy/function-level
# imports cause the first PcapReader in a fresh process to warn
# "unknown LL type" and fall back to Raw, silently dropping all IP/TCP/UDP
# header information for that file (train/inference mismatch).
from scapy.utils import PcapReader  # noqa: E402
from scapy.layers.inet import IP, TCP, UDP  # noqa: E402
from scapy.layers.l2 import Ether  # noqa: E402


def parse_packet(pkt):
    """Parse one scapy packet with header validation. Never raises.

    Returns dict with length/time/proto/flags/src/dst or None if
    packet is malformed/empty.
    """
    try:
        length = len(pkt)
    except Exception:
        return None
    try:
        t = float(pkt.time)
    except Exception:
        return None
    if length <= 0:
        return None

    has_ip = False
    src = dst = None
    try:
        has_ip = pkt.haslayer(IP)
    except Exception:
        has_ip = False
    if has_ip:
        try:
            ip = pkt[IP]
            src = str(ip.src)
            dst = str(ip.dst)
        except Exception:
            has_ip = False
            src = dst = None

    is_tcp = False
    is_udp = False
    syn = ack = fin = rst = psh = 0
    try:
        is_tcp = bool(pkt.haslayer(TCP))
    except Exception:
        is_tcp = False
    try:
        is_udp = bool(pkt.haslayer(UDP)) and not is_tcp
    except Exception:
        is_udp = False
    if is_tcp:
        try:
            flags = pkt[TCP].flags
            fint = int(flags)
            fin = 1 if (fint & 0x01) else 0
            syn = 1 if (fint & 0x02) else 0
            rst = 1 if (fint & 0x04) else 0
            psh = 1 if (fint & 0x08) else 0
            ack = 1 if (fint & 0x10) else 0
        except Exception:
            syn = ack = fin = rst = psh = 0

    return {
        "length": float(length),
        "time": t,
        "is_tcp": 1 if is_tcp else 0,
        "is_udp": 1 if is_udp else 0,
        "syn": syn, "ack": ack, "fin": fin, "rst": rst, "psh": psh,
        "src": src, "dst": dst, "has_ip": has_ip,
    }


def finalize_window(raw_packets):
    """Add window-local iat + direction, return list ready for window_to_feature."""
    if not raw_packets:
        return []
    # reference: first packet in window with valid IP
    ref = None
    for p in raw_packets:
        if p["has_ip"] and p["src"]:
            ref = p["src"]
            break
    out = []
    for i, p in enumerate(raw_packets):
        if i == 0:
            iat = 0.0
        else:
            try:
                iat = max(0.0, float(p["time"]) - float(raw_packets[i - 1]["time"]))
            except Exception:
                iat = 0.0
        if not p["has_ip"] or ref is None:
            direction = 0
        else:
            if p["src"] == ref:
                direction = 1
            elif p["dst"] == ref:
                direction = -1
            else:
                direction = 0  # third host / multi-flow window
        out.append({
            "length": p["length"], "time": p["time"], "iat": iat,
            "is_tcp": p["is_tcp"], "is_udp": p["is_udp"],
            "syn": p["syn"], "ack": p["ack"], "fin": p["fin"],
            "rst": p["rst"], "psh": p["psh"],
            "direction": direction,
        })
    return out


def extract_capture(capture_path: Path, max_packets=MAX_PACKETS_PER_CAPTURE,
                    window_size=WINDOW_SIZE):
    """Extract windows from one capture. Returns (windows, stats)."""
    stats = {"packets_read": 0, "packets_usable": 0, "malformed": 0,
             "truncated": False, "error": ""}
    raw = []
    try:
        with PcapReader(str(capture_path)) as reader:
            for pkt in reader:
                stats["packets_read"] += 1
                if len(raw) >= max_packets:
                    stats["truncated"] = True
                    # still count remaining? break to bound runtime
                    break
                parsed = parse_packet(pkt)
                if parsed is None:
                    stats["malformed"] += 1
                    continue
                raw.append(parsed)
                stats["packets_usable"] += 1
        # If truncated, we stopped early; note it.
    except Exception as e:
        stats["error"] = str(e)[:500]
        return [], stats
    # partition into non-overlapping windows
    windows = []
    for start in range(0, len(raw), window_size):
        chunk = raw[start:start + window_size]
        if len(chunk) < 5:
            # skip tiny tail windows (not enough for stats)
            stats.setdefault("skipped_tiny_windows", 0)
            stats["skipped_tiny_windows"] += 1
            continue
        finalized = finalize_window(chunk)
        feat = window_to_feature(finalized)
        seq = window_to_sequence(finalized, seq_len=SEQ_LEN)
        if feat is None:
            continue
        windows.append((feat, seq))
    stats["n_windows"] = len(windows)
    return windows, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default=str(PROCESSED_DIR / "capture_inventory.csv"))
    ap.add_argument("--out-csv", default=str(PROCESSED_DIR / "features_windows.csv"))
    ap.add_argument("--out-npz", default=str(PROCESSED_DIR / "features_sequences.npz"))
    ap.add_argument("--max-packets", type=int, default=MAX_PACKETS_PER_CAPTURE)
    ap.add_argument("--window", type=int, default=WINDOW_SIZE)
    args = ap.parse_args()

    inv_path = Path(args.inventory)
    if not inv_path.exists():
        raise SystemExit(f"Inventory not found: {inv_path}. Run create_inventory.py first.")

    import csv as csvmod
    with open(inv_path, newline="", encoding="utf-8") as f:
        inv_rows = list(csvmod.DictReader(f))

    t_start = time.time()
    all_rows = []
    seqs, y_list, groups, sample_ids = [], [], [], []
    log = {"captures": {}, "errors": []}
    total_windows = 0

    for row in inv_rows:
        rel = row["relative_path"]
        cap_path = PROJECT_ROOT / rel
        vpn_label = row["vpn_label"]
        app_label = row["app_label_prelim"]
        if vpn_label not in LABEL_MAPPING:
            log["errors"].append(f"{rel}: unsupported vpn label '{vpn_label}' skipped")
            continue
        if not cap_path.exists():
            log["errors"].append(f"{rel}: file missing, skipped")
            continue
        print(f"Processing {cap_path.name} ...", flush=True)
        windows, stats = extract_capture(cap_path, max_packets=args.max_packets,
                                         window_size=args.window)
        log["captures"][rel] = stats
        if stats.get("error"):
            log["errors"].append(f"{rel}: {stats['error']}")
        if not windows:
            log["errors"].append(f"{rel}: no usable windows, skipped")
            continue
        label_id = LABEL_MAPPING[vpn_label]
        for wi, (feat, seq) in enumerate(windows):
            sid = f"{cap_path.stem}__w{wi:04d}"
            rec = {"sample_id": sid, "capture_path": rel, "group": cap_path.name,
                   "vpn_label": vpn_label, "vpn_label_id": label_id,
                   "app_label_prelim": app_label}
            for name, val in zip(FEATURE_NAMES, feat):
                rec[name] = val
            all_rows.append(rec)
            seqs.append(seq)
            y_list.append(label_id)
            groups.append(cap_path.name)
            sample_ids.append(sid)
        total_windows += len(windows)
        print(f"  -> {len(windows)} windows (read={stats['packets_read']}, usable={stats['packets_usable']}, malformed={stats['malformed']}, truncated={stats['truncated']})", flush=True)

    # save CSV
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if all_rows:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)
    # save NPZ sequences
    out_npz = Path(args.out_npz)
    if seqs:
        np.savez_compressed(out_npz,
                            X=np.stack(seqs).astype(np.float32),
                            y=np.array(y_list, dtype=np.int64),
                            groups=np.array(groups),
                            sample_ids=np.array(sample_ids))
    # schema + mapping
    with open(PROCESSED_DIR / "feature_schema.json", "w") as f:
        json.dump({"feature_names": FEATURE_NAMES, "order": FEATURE_NAMES,
                   "window_size": args.window, "max_packets_per_capture": args.max_packets,
                   "seq_len": SEQ_LEN, "seq_channels": ["pkt_len", "iat", "direction", "is_tcp", "is_udp"],
                   "model_version": "1.0.0"}, f, indent=2)
    with open(PROCESSED_DIR / "label_mapping.json", "w") as f:
        json.dump({"vpn_label_mapping": LABEL_MAPPING, "notes": "0=nonvpn, 1=vpn"}, f, indent=2)
    log["summary"] = {"n_captures_processed": len(log["captures"]),
                      "n_windows": total_windows,
                      "duration_sec": time.time() - t_start,
                      "max_packets_per_capture": args.max_packets,
                      "window_size": args.window}
    with open(PROCESSED_DIR / "extraction_log.json", "w") as f:
        json.dump(log, f, indent=2)
    print(f"\nWrote {out_csv} ({len(all_rows)} windows)")
    print(f"Wrote {out_npz}")
    print(f"Duration: {time.time()-t_start:.1f}s")
    if log["errors"]:
        print("ERRORS/WARNINGS:")
        for e in log["errors"]:
            print(" -", e)


if __name__ == "__main__":
    main()
