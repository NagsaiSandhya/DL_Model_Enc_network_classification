"""Python ML micro-service exposing the existing VPN/non-VPN pipeline.

Reuses src/predict.py::predict_capture and src/extract_features parsing
(no reimplemented feature logic, no mock predictions).

Run from demo1/ with the existing .venv:
    .venv\\Scripts\\activate
    python -m uvicorn ml_service.app:app --port 8000
"""
import os
import sys
import time
import uuid
from pathlib import Path

# --- make src/ importable (project-relative, no hardcoded absolute paths) ---
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# CRITICAL: import scapy layers at module top before any PcapReader is made
# (see src/extract_features.py for why lazy imports corrupt decoding).
from scapy.layers.inet import IP, TCP, UDP  # noqa: E402
from scapy.layers.l2 import Ether  # noqa: E402
from scapy.utils import PcapReader  # noqa: E402

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from common import FEATURE_NAMES, LABEL_MAPPING, MODEL_VERSION  # noqa: E402
from predict import DEFAULT_MODEL, SUPPORTED_TASKS  # noqa: E402

MAX_UPLOAD_BYTES = int(os.environ.get("ML_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))
CHART_SCAN_PACKETS = int(os.environ.get("ML_CHART_SCAN_PACKETS", "5000"))
ALLOWED_EXTS = (".pcap", ".pcapng")

app = FastAPI(title="Encrypted Traffic ML Service")

_model_meta_cache = {}


def _load_artifact_meta():
    import pickle

    if _model_meta_cache:
        return _model_meta_cache
    if not Path(str(DEFAULT_MODEL)).exists():
        return {"available": False}
    with open(str(DEFAULT_MODEL), "rb") as f:
        art = pickle.load(f)
    _model_meta_cache.update(
        {
            "available": True,
            "model_version": art.get("model_version", MODEL_VERSION),
            "task": art.get("task", "vpn_vs_nonvpn"),
            "config": art.get("config", {}),
            "metrics": art.get("metrics", {}),
            "dependencies": art.get("dependencies", {}),
            "label_mapping": art.get("label_mapping", LABEL_MAPPING),
            "n_features": len(art.get("feature_names", FEATURE_NAMES)),
        }
    )
    # verified test metrics if present
    try:
        import json

        mpath = _PROJECT_ROOT / "results" / "metrics" / "vpn_metrics.json"
        if mpath.exists():
            m = json.load(open(mpath))["test"]
            _model_meta_cache["verified_test_metrics"] = {
                "accuracy": m["accuracy"],
                "f1_weighted": m["f1_weighted"],
                "confusion_matrix": m["confusion_matrix"],
            }
    except Exception:
        pass
    return _model_meta_cache


def _chart_stats(path: Path):
    """Descriptive packet stats for charts (NOT model features).

    Scans up to CHART_SCAN_PACKETS packets: length histogram, IAT
    histogram, protocol distribution. Returns None-fields when
    unavailable instead of fabricating.
    """
    lengths, iats, protos = [], [], {"tcp": 0, "udp": 0, "other": 0}
    prev_t = None
    n = 0
    try:
        with PcapReader(str(path)) as reader:
            for pkt in reader:
                if n >= CHART_SCAN_PACKETS:
                    break
                try:
                    lengths.append(len(pkt))
                except Exception:
                    continue
                try:
                    t = float(pkt.time)
                    if prev_t is not None:
                        iats.append(max(0.0, t - prev_t))
                    prev_t = t
                except Exception:
                    pass
                try:
                    if pkt.haslayer(TCP):
                        protos["tcp"] += 1
                    elif pkt.haslayer(UDP):
                        protos["udp"] += 1
                    else:
                        protos["other"] += 1
                except Exception:
                    protos["other"] += 1
                n += 1
    except Exception:
        return {"scanned_packets": n, "unavailable": True}
    if not lengths:
        return {"scanned_packets": 0, "unavailable": True}
    import numpy as np

    la = np.array(lengths, dtype=float)
    len_bins = [0, 100, 500, 1000, 1500, float("inf")]
    len_labels = ["0-100", "100-500", "500-1000", "1000-1500", "1500+"]
    len_hist, _ = np.histogram(la, bins=len_bins)
    out = {
        "scanned_packets": int(n),
        "packet_length_hist": {
            "bins": len_labels,
            "counts": [int(c) for c in len_hist],
            "min": float(la.min()),
            "max": float(la.max()),
            "mean": float(la.mean()),
        },
        "protocol_distribution": {k: int(v) for k, v in protos.items()},
    }
    if iats:
        ia = np.array(iats, dtype=float)
        iat_bins = [0, 0.001, 0.01, 0.1, 1.0, float("inf")]
        iat_labels = ["<1ms", "1-10ms", "10-100ms", "100ms-1s", ">1s"]
        hist, _ = np.histogram(ia, bins=iat_bins)
        out["iat_hist"] = {
            "bins": iat_labels,
            "counts": [int(c) for c in hist],
            "mean": float(ia.mean()),
        }
    else:
        out["iat_hist"] = None
    return out


@app.get("/health")
def health():
    meta = _load_artifact_meta()
    return {
        "status": "ok",
        "model_loaded": bool(meta.get("available")),
        "model_version": meta.get("model_version"),
    }


@app.get("/model-info")
def model_info():
    meta = _load_artifact_meta()
    if not meta.get("available"):
        raise HTTPException(status_code=503, detail="Model artifact unavailable.")
    return {
        "tasks": [f"vpn_vs_nonvpn ({'/'.join(SUPPORTED_TASKS)})"],
        "supported_task_ids": list(SUPPORTED_TASKS),
        "model_name": "vpn_classifier",
        "model_version": meta.get("model_version"),
        "n_features": meta.get("n_features"),
        "label_mapping": meta.get("label_mapping"),
        "config": meta.get("config"),
        "metrics": meta.get("metrics"),
        "verified_test_metrics": meta.get("verified_test_metrics"),
        "notes": "VPN vs non-VPN only. Application-level classification is not a validated model.",
    }


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    fname = (file.filename or "").lower()
    if not fname.endswith(ALLOWED_EXTS):
        raise HTTPException(
            status_code=400,
            detail="Please select a PCAP or PCAPNG file.",
        )
    tmpdir = _PROJECT_ROOT / "ml_service" / "tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)
    suffix = ".pcapng" if fname.endswith(".pcapng") else ".pcap"
    tmp_path = tmpdir / f"{uuid.uuid4().hex}{suffix}"
    try:
        size = 0
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="This file is larger than the allowed upload limit.",
                    )
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        from predict import predict_capture

        t0 = time.time()
        try:
            res = predict_capture(str(tmp_path), task="vpn")
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=f"The selected capture could not be read. ({e})")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        charts = _chart_stats(tmp_path)
        return JSONResponse(
            {
                "success": True,
                "analysis": {
                    "task": "vpn_vs_nonvpn",
                    "predicted_label": res["predicted_class"],
                    "probabilities": res["class_probabilities"],
                    "model_version": res.get("model_version"),
                    "packet_count": res["n_packets"],
                    "feature_sample_count": res["n_windows"],
                    "window_votes": res.get("window_votes"),
                    "processing_time_seconds": round(res.get("duration_sec", time.time() - t0), 3),
                    "warnings": res.get("warnings", []),
                    "charts": charts,
                    "disclaimer": "This is a machine-learning prediction, not a guarantee. Accuracy may vary depending on capture quality and how closely the traffic resembles the training data.",
                },
            }
        )
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
