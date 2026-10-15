"""Generate data/processed/capture_inventory.csv (fast, dpkt-based)."""
import argparse
import csv
import time
from pathlib import Path

from common import (
    PROJECT_ROOT, RAW_NONVPN_DIR, RAW_VPN_DIR, PROCESSED_DIR,
    infer_vpn_label, infer_app_label,
)

try:
    from dpkt import pcap as dpkt_pcap
    from dpkt import pcapng as dpkt_pcapng
    HAS_DPKT = True
except Exception:
    HAS_DPKT = False

try:
    from scapy.utils import PcapReader
    from scapy.layers.inet import IP, TCP, UDP
    from scapy.layers.l2 import Ether
    HAS_SCAPY = True
except Exception:
    HAS_SCAPY = False


def count_packets_dpkt(path: Path):
    """Fast packet count via dpkt. Tries format by extension, falls back
    to the other reader (handles .pcap files that are actually pcapng)."""
    def _count(reader):
        count = 0
        for _ts, _buf in reader:
            count += 1
        return count
    suffix = path.suffix.lower()
    # order to try based on extension
    errors = []
    if suffix == ".pcapng":
        order = ("pcapng", "pcap")
    else:
        order = ("pcap", "pcapng")
    for kind in order:
        try:
            with open(path, "rb") as f:
                if kind == "pcapng":
                    reader = dpkt_pcapng.Reader(f)
                else:
                    reader = dpkt_pcap.Reader(f)
                count = _count(reader)
            note = "" if kind == order[0] else f"info:extension-{suffix}-parsed-as-{kind}"
            return count, "", note, ""
        except Exception as e:
            errors.append(f"{kind}:{e}")
    return 0, "", "", f"dpkt read error: {' | '.join(errors)}"


def probe_linktype_scapy(path: Path, n_probe=3):
    """Read linktype + first-packet layer validity via scapy (slow, only probe)."""
    if not HAS_SCAPY:
        return "", "scapy unavailable", ""
    try:
        linktype = ""
        warnings = []
        with PcapReader(str(path)) as reader:
            try:
                linktype = str(getattr(reader, "linktype", ""))
            except Exception:
                linktype = ""
            for i, pkt in enumerate(reader):
                if i >= n_probe:
                    break
                try:
                    has_ip = pkt.haslayer(IP)
                except Exception:
                    has_ip = False
                if not has_ip and i == 0:
                    warnings.append("first-packet-no-IP-layer")
                # detect Raw fallback: no Ether but has IP
                try:
                    has_ether = pkt.haslayer(Ether)
                    if not has_ether and has_ip:
                        warnings.append("no-Ethernet-RAW-IP")
                except Exception:
                    pass
        return linktype, ";".join(sorted(set(warnings))), ""
    except Exception as e:
        return "", "", f"scapy probe error: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(PROCESSED_DIR / "capture_inventory.csv"))
    args = ap.parse_args()

    search_dirs = [RAW_NONVPN_DIR, RAW_VPN_DIR]
    files = []
    for d in search_dirs:
        if not d.exists():
            print(f"WARNING: missing dir {d}")
            continue
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".pcap", ".pcapng"}:
                files.append(p)

    print(f"Found {len(files)} capture files")
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for path in files:
        rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        size = path.stat().st_size
        fname = path.name
        vpn_label = infer_vpn_label(rel)  # nonvpn checked BEFORE vpn
        app_label = infer_app_label(fname)

        t0 = time.time()
        pkt_count, link_dpkt, note_dpkt, err = count_packets_dpkt(path)
        # scapy linktype probe (fast: only first packets)
        linktype, warn_scapy, err_scapy = probe_linktype_scapy(path)
        if err_scapy and not err:
            err = err_scapy
        # Separate real warnings (affect validation_status) from info notes.
        # For DLT_RAW(101) captures, "no-Ethernet-RAW-IP" is EXPECTED, not a
        # data-quality issue: headers are validated per-packet and IP/TCP are
        # still available. Demote it to info in that case.
        scapy_warns = [w for w in warn_scapy.split(";") if w] if warn_scapy else []
        real_warnings = []
        info_notes = [w for w in [note_dpkt] if w]
        for w in scapy_warns:
            if w == "no-Ethernet-RAW-IP":
                # Investigated: VPN captures use DLT_RAW (no Ethernet) and
                # NonVPN use Ethernet; both still carry IP/TCP after per-packet
                # validation. This is informational, not a data-quality warning.
                info_notes.append("info:RAW-IP-no-Ethernet-validated-per-packet")
            else:
                real_warnings.append(w)
        # link-layer info (not a data-quality warning by itself)
        if linktype == "101":
            info_notes.append("info:DLT_RAW(101)-no-Ethernet-expect-IP-only")
        elif linktype == "1":
            info_notes.append("info:DLT_EN10MB(1)-Ethernet-expected")
        elif linktype in ("", "None"):
            info_notes.append("info:linktype-n/a-pcapng-validated-per-packet")

        if vpn_label == "unknown" or app_label == "unknown":
            real_warnings.append("ambiguous-label")
        if pkt_count == 0 and not err:
            real_warnings.append("empty-or-unreadable")

        warnings = ";".join([w for w in real_warnings if w])
        info_str = ";".join([w for w in info_notes if w])
        combined = ";".join([s for s in [warnings, info_str] if s])

        status = "error" if (err or pkt_count == 0) else ("warning" if warnings else "valid")
        rows.append({
            "relative_path": rel,
            "filename": fname,
            "file_size_bytes": size,
            "packet_count": pkt_count,
            "vpn_label": vpn_label,
            "app_label_prelim": app_label,
            "linktype": linktype,
            "validation_status": status,
            "warnings_errors": (combined + (" | " + err if err else ""))[:1000],
        })
        print(f"{fname:32s} packets={pkt_count:8d} vpn={vpn_label:7s} app={app_label:16s} link={linktype:6s} {status}")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
