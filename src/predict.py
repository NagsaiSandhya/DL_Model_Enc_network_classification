"""Reusable inference module for the future website.

Website should call:
    from predict import predict_capture
    result = predict_capture("path/to/capture.pcap", task="vpn")

Returns dict with: predicted_class, class_scores/probabilities,
n_packets, n_windows (usable flows), warnings, duration, etc.
Uses EXACTLY the same feature extraction as training (common.py +
extract_features.extract_capture).
"""
import argparse
import pickle
import time
from pathlib import Path

from common import (
    PROJECT_ROOT, PROCESSED_DIR, MODELS_DIR, FEATURE_NAMES,
    LABEL_MAPPING, INV_LABEL_MAPPING, MAX_PACKETS_PER_CAPTURE, WINDOW_SIZE,
)

DEFAULT_MODEL = MODELS_DIR / "vpn_classifier.pkl"
SUPPORTED_TASKS = ("vpn",)


def _load_trusted_model(model_path: Path):
    """Load only trusted model artifacts from the project's models dir."""
    model_path = Path(model_path)
    # Resolve and ensure inside project models dir OR explicitly the default.
    try:
        resolved = model_path.resolve()
        trusted_dir = MODELS_DIR.resolve()
        is_inside = str(resolved).startswith(str(trusted_dir))
    except Exception:
        is_inside = False
    if not is_inside:
        raise ValueError(
            f"Refusing to load untrusted model artifact: {model_path}. "
            f"Only artifacts under {MODELS_DIR} are trusted. "
            "Do not load arbitrary uploaded pickle files."
        )
    if not resolved.exists():
        raise FileNotFoundError(f"Model artifact not found: {resolved}")
    with open(resolved, "rb") as f:
        artifact = pickle.load(f)
    # schema check
    if list(artifact.get("feature_names", [])) != FEATURE_NAMES:
        raise ValueError("Model feature schema does not match training schema.")
    return artifact


def predict_capture(capture_path, task="vpn", model_path=None, max_packets=MAX_PACKETS_PER_CAPTURE):
    """Predict VPN vs non-VPN for one capture file.

    Args:
        capture_path: path to .pcap/.pcapng file.
        task: must be 'vpn'. Other tasks raise a controlled error.
        model_path: trusted .pkl under models/. Defaults to vpn_classifier.pkl.
        max_packets: cap packets read (same default as training).

    Returns dict:
        predicted_class, class_probabilities, n_packets, n_windows,
        per_window_predictions, warnings, duration_sec, model_version, task
    Raises ValueError/FileNotFoundError with controlled messages for invalid input.
    """
    t0 = time.time()
    warnings = []
    if task not in SUPPORTED_TASKS:
        raise ValueError(
            f"Unsupported task '{task}'. Supported tasks: {list(SUPPORTED_TASKS)}. "
            "Application classification is not implemented as a separate validated model."
        )
    cap = Path(capture_path)
    if not str(cap).lower().endswith((".pcap", ".pcapng")):
        # allow Path objects without suffix check bypass? enforce
        raise ValueError(f"Unsupported file type: {cap}. Expected .pcap or .pcapng.")
    if not cap.exists():
        raise FileNotFoundError(f"Capture not found: {cap}")

    from extract_features import extract_capture
    windows, stats = extract_capture(cap, max_packets=max_packets, window_size=WINDOW_SIZE)
    if stats.get("error"):
        raise ValueError(f"Could not parse capture: {stats['error']}")
    n_packets = int(stats.get("packets_usable", 0))
    if stats.get("truncated"):
        warnings.append(f"info:truncated-to-first-{max_packets}-packets-like-training")
    if stats.get("malformed"):
        warnings.append(f"info:{stats['malformed']}-malformed-packets-skipped")
    if not windows:
        raise ValueError("No usable windows extracted (empty capture or all packets malformed).")

    import numpy as np
    X = np.array([feat for feat, _seq in windows], dtype=float)
    # verify schema order
    assert X.shape[1] == len(FEATURE_NAMES)

    artifact = _load_trusted_model(Path(model_path) if model_path else DEFAULT_MODEL)
    pipe = artifact["pipeline"]
    proba = pipe.predict_proba(X) if hasattr(pipe, "predict_proba") else None
    preds = pipe.predict(X)

    # aggregate: majority vote + mean probability
    counts = {0: int((preds == 0).sum()), 1: int((preds == 1).sum())}
    majority = int(0 if counts[0] >= counts[1] else 1)
    mean_proba = None
    class_probabilities = {}
    if proba is not None:
        mean_proba = proba.mean(axis=0)
        classes = list(pipe.classes_)
        for cls, p in zip(classes, mean_proba):
            class_probabilities[INV_LABEL_MAPPING.get(int(cls), str(cls))] = float(p)
    else:
        for k in (0, 1):
            class_probabilities[INV_LABEL_MAPPING[k]] = float(counts[k] / len(preds))

    result = {
        "task": task,
        "predicted_class": INV_LABEL_MAPPING[majority],
        "predicted_class_id": majority,
        "class_probabilities": class_probabilities,  # mean over windows; NOT calibrated
        "n_packets": n_packets,
        "n_packets_read": int(stats.get("packets_read", n_packets)),
        "n_windows": int(len(windows)),
        "window_votes": {"nonvpn": counts[0], "vpn": counts[1]},
        "warnings": warnings,
        "duration_sec": time.time() - t0,
        "model_version": artifact.get("model_version"),
        "model_path": str(model_path if model_path else DEFAULT_MODEL),
        "notes": "Probabilities are raw RandomForest vote fractions, not calibrated.",
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="path to capture .pcap/.pcapng")
    ap.add_argument("--task", default="vpn")
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    args = ap.parse_args()
    try:
        res = predict_capture(args.input, task=args.task, model_path=args.model)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        raise SystemExit(2)
    import json
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
