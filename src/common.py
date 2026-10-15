"""Shared constants and feature-extraction logic.

Single source of truth for training and inference so both use
exactly the same pipeline.
"""
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_NONVPN_DIR = PROJECT_ROOT / "data" / "raw" / "NonVPN-PCAPs-01"
RAW_VPN_DIR = PROJECT_ROOT / "data" / "raw" / "VPN-PCAPS-01"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
RESULTS_METRICS_DIR = PROJECT_ROOT / "results" / "metrics"
RESULTS_FIGURES_DIR = PROJECT_ROOT / "results" / "figures"

RANDOM_SEED = 42
MAX_PACKETS_PER_CAPTURE = 20000
WINDOW_SIZE = 50

# Ordered feature names - must never change order without version bump.
FEATURE_NAMES = [
    "n_packets",
    "duration",
    "total_bytes",
    "mean_len",
    "std_len",
    "min_len",
    "max_len",
    "mean_iat",
    "std_iat",
    "min_iat",
    "max_iat",
    "pkt_rate",
    "byte_rate",
    "tcp_ratio",
    "udp_ratio",
    "other_proto_ratio",
    "tcp_syn_ratio",
    "tcp_ack_ratio",
    "tcp_fin_ratio",
    "tcp_rst_ratio",
    "tcp_psh_ratio",
    "fwd_ratio",
    "bwd_ratio",
    "unknown_dir_ratio",
]

SEQ_LEN = WINDOW_SIZE
SEQ_CHANNELS = ["pkt_len", "iat", "direction", "is_tcp", "is_udp"]
SEQ_FEATURE_NAMES = SEQ_CHANNELS

LABEL_MAPPING = {"nonvpn": 0, "vpn": 1}
INV_LABEL_MAPPING = {v: k for k, v in LABEL_MAPPING.items()}

MODEL_VERSION = "1.0.0"


def infer_vpn_label(path_str: str) -> str:
    """Infer vpn/nonvpn label. Check nonvpn BEFORE vpn.

    'nonvpn' contains substring 'vpn', so checking 'vpn' first
    would mislabel every non-VPN capture as VPN.
    """
    low = path_str.lower().replace("\\", "/")
    if "nonvpn" in low:
        return "nonvpn"
    if "vpn" in low:
        return "vpn"
    return "unknown"


def infer_app_label(filename: str) -> str:
    """Preliminary application label from filename. Returns 'unknown' if ambiguous."""
    low = filename.lower()
    # order matters: specific before generic
    if "bittorrent" in low:
        return "bittorrent"
    if "ftps" in low:
        return "ftps"
    if "hangouts" in low:
        if "audio" in low:
            return "hangouts_audio"
        if "chat" in low:
            return "hangouts_chat"
        return "hangouts_unknown"
    if "facebook" in low:
        if "audio" in low:
            return "facebook_audio"
        if "video" in low:
            return "facebook_video"
        if "chat" in low:
            return "facebook_chat"
        return "facebook_unknown"
    if "aim" in low or "aimchat" in low:
        return "aim_chat"
    if "email" in low:
        return "email"
    return "unknown"


def window_to_feature(packets):
    """Convert a list of per-packet dicts to the 24-dim feature vector.

    Each packet dict must have: length (int/float), iat (float),
    is_tcp (0/1), is_udp (0/1), tcp flags (syn/ack/fin/rst/psh 0/1, only
    meaningful if is_tcp), direction (+1 fwd / -1 bwd / 0 unknown).

    Never invents values: ratios fall back to 0.0 when denominator is 0.
    """
    n = len(packets)
    if n == 0:
        return None
    lengths = np.array([p["length"] for p in packets], dtype=float)
    iats = np.array([p["iat"] for p in packets], dtype=float)
    # first packet iat is defined as 0.0 by caller
    iats_nz = iats[1:] if n > 1 else np.array([0.0])
    times = np.array([p["time"] for p in packets], dtype=float)
    duration = float(times[-1] - times[0]) if n > 1 else 0.0
    total_bytes = float(lengths.sum())

    def _stats(a):
        a = np.asarray(a, dtype=float)
        if len(a) == 0:
            return 0.0, 0.0, 0.0, 0.0
        return float(a.mean()), float(a.std()), float(a.min()), float(a.max())

    mean_len, std_len, min_len, max_len = _stats(lengths)
    if n > 1:
        mean_iat, std_iat, min_iat, max_iat = _stats(iats_nz)
    else:
        mean_iat = std_iat = min_iat = max_iat = 0.0

    pkt_rate = float(n / duration) if duration > 0 else 0.0
    byte_rate = float(total_bytes / duration) if duration > 0 else 0.0

    is_tcp = np.array([p["is_tcp"] for p in packets], dtype=float)
    is_udp = np.array([p["is_udp"] for p in packets], dtype=float)
    tcp_ratio = float(is_tcp.mean())
    udp_ratio = float(is_udp.mean())
    other_proto_ratio = float(max(0.0, 1.0 - tcp_ratio - udp_ratio))

    n_tcp = int(is_tcp.sum())
    if n_tcp > 0:
        syn = float(np.mean([p["syn"] for p in packets if p["is_tcp"]]))
        ack = float(np.mean([p["ack"] for p in packets if p["is_tcp"]]))
        fin = float(np.mean([p["fin"] for p in packets if p["is_tcp"]]))
        rst = float(np.mean([p["rst"] for p in packets if p["is_tcp"]]))
        psh = float(np.mean([p["psh"] for p in packets if p["is_tcp"]]))
    else:
        syn = ack = fin = rst = psh = 0.0

    dirs = np.array([p["direction"] for p in packets])
    fwd_ratio = float(np.mean(dirs == 1))
    bwd_ratio = float(np.mean(dirs == -1))
    unknown_dir_ratio = float(np.mean(dirs == 0))

    return [
        float(n), duration, total_bytes,
        mean_len, std_len, min_len, max_len,
        mean_iat, std_iat, min_iat, max_iat,
        pkt_rate, byte_rate,
        tcp_ratio, udp_ratio, other_proto_ratio,
        syn, ack, fin, rst, psh,
        fwd_ratio, bwd_ratio, unknown_dir_ratio,
    ]


def window_to_sequence(packets, seq_len=SEQ_LEN):
    """Convert packet window to (seq_len, 5) sequence for 1D-CNN.

    Channels: [pkt_len, iat, direction, is_tcp, is_udp].
    Pads with zeros or truncates to seq_len. This is a genuine
    sequential representation (ordered packet series), not
    arbitrary tabular features.
    """
    seq = np.zeros((seq_len, 5), dtype=np.float32)
    for i, p in enumerate(packets[:seq_len]):
        seq[i, 0] = float(p["length"])
        seq[i, 1] = float(p["iat"])
        seq[i, 2] = float(p["direction"])
        seq[i, 3] = float(p["is_tcp"])
        seq[i, 4] = float(p["is_udp"])
    return seq
