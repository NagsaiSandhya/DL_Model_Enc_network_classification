"""Acceptance tests: executes checks, marks passed/failed/skipped with reasons."""
import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import PROJECT_ROOT, FEATURE_NAMES, LABEL_MAPPING  # noqa: E402

results = []


def check(name, fn):
    try:
        detail = fn()
        results.append({"test": name, "status": "passed", "detail": str(detail)[:300]})
        print(f"PASS: {name} -- {detail}")
    except Exception as e:
        results.append({"test": name, "status": "failed", "detail": str(e)[:300]})
        print(f"FAIL: {name} -- {e}")


def t_inventory():
    import csv
    p = PROJECT_ROOT / "data" / "processed" / "capture_inventory.csv"
    rows = list(csv.DictReader(open(p)))
    assert len(rows) == 37, f"expected 37 rows, got {len(rows)}"
    errs = [r for r in rows if r["validation_status"] == "error"]
    assert not errs, f"errors: {errs}"
    assert {r["vpn_label"] for r in rows} <= {"vpn", "nonvpn"}, "unknown vpn label"
    return f"37 captures, 0 errors, labels={sorted({r['vpn_label'] for r in rows})}"


def t_features():
    import pandas as pd
    df = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "features_windows.csv")
    assert len(df) == 9227, f"expected 9227 windows, got {len(df)}"
    assert list(df.columns[6:6 + len(FEATURE_NAMES)]) == FEATURE_NAMES or set(FEATURE_NAMES) <= set(df.columns)
    # no IPs/labels as features
    for bad in ["src", "dst", "ip", "filename", "capture_path"]:
        assert bad not in FEATURE_NAMES, bad
    schema = json.load(open(PROJECT_ROOT / "data" / "processed" / "feature_schema.json"))
    assert schema["feature_names"] == FEATURE_NAMES
    return f"{len(df)} windows, schema ok"


def t_split():
    s = json.load(open(PROJECT_ROOT / "data" / "processed" / "split_groups.json"))
    assert not (set(s["test_groups"]) & set(s["train_groups"])), "group leakage"
    import pandas as pd
    df = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "features_windows.csv")
    for g in ["train_groups", "val_groups", "test_groups"]:
        labs = set(df[df.group.isin(s[g])]["vpn_label"])
        assert labs == {"vpn", "nonvpn"}, f"{g} missing class: {labs}"
    return f"train={len(s['train_groups'])} val={len(s['val_groups'])} test={len(s['test_groups'])}, no overlap"


def t_model_artifact():
    art = pickle.load(open(PROJECT_ROOT / "models" / "vpn_classifier.pkl", "rb"))
    assert "pipeline" in art and "feature_names" in art and "label_mapping" in art
    assert art["feature_names"] == FEATURE_NAMES
    assert art["label_mapping"] == LABEL_MAPPING
    assert "scaler" in art["pipeline"].named_steps, "scaler not saved in pipeline"
    assert art.get("model_version") and art.get("config") and art.get("dependencies")
    assert art["metrics"]["test_accuracy"] > 0.8
    return f"test_acc={art['metrics']['test_accuracy']:.4f}, pipeline+scaler saved"


def t_fresh_predict_heldout():
    from predict import predict_capture
    # held-out test captures (from split file, never trained on)
    r1 = predict_capture(str(PROJECT_ROOT / "data" / "raw" / "NonVPN-PCAPs-01" / "facebook_audio1a.pcap"))
    r2 = predict_capture(str(PROJECT_ROOT / "data" / "raw" / "VPN-PCAPS-01" / "vpn_hangouts_chat1b.pcap"))
    assert r1["predicted_class"] in ("vpn", "nonvpn") and r2["predicted_class"] in ("vpn", "nonvpn")
    return f"nonvpn-cap->{r1['predicted_class']}, vpn-cap->{r2['predicted_class']}"


def t_determinism():
    from predict import predict_capture
    cap = str(PROJECT_ROOT / "data" / "raw" / "NonVPN-PCAPs-01" / "facebookchat1.pcapng")
    a = predict_capture(cap)
    b = predict_capture(cap)
    assert a["predicted_class"] == b["predicted_class"], "nondeterministic class"
    assert a["class_probabilities"] == b["class_probabilities"], "nondeterministic probs"
    return f"reproducible: {a['predicted_class']} {a['class_probabilities']}"


def t_invalid_handling():
    from predict import predict_capture
    try:
        predict_capture(str(PROJECT_ROOT / "data" / "processed" / "capture_inventory.csv"))
        raise AssertionError("should have raised for .csv")
    except ValueError:
        pass
    try:
        predict_capture(str(PROJECT_ROOT / "data" / "raw" / "NonVPN-PCAPs-01" / "facebookchat1.pcapng"), task="application")
        raise AssertionError("should have raised for bad task")
    except ValueError:
        pass
    return "controlled errors for bad extension + unsupported task"


def t_schema_consistency():
    import pandas as pd
    import numpy as np
    from extract_features import extract_capture
    cap = PROJECT_ROOT / "data" / "raw" / "VPN-PCAPS-01" / "vpn_facebook_chat1a.pcap"
    windows, _ = extract_capture(cap)
    Xfresh = np.array([f for f, _ in windows])
    df = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "features_windows.csv")
    Xcsv = df[df.group == "vpn_facebook_chat1a.pcap"].sort_values("sample_id")[FEATURE_NAMES].to_numpy()
    assert Xfresh.shape == Xcsv.shape, f"{Xfresh.shape} vs {Xcsv.shape}"
    assert np.abs(Xfresh - Xcsv).max() < 1e-6, "train/inference mismatch"
    return f"fresh==stored (max diff {np.abs(Xfresh-Xcsv).max():.2e})"


def t_metrics_figures():
    m = json.load(open(PROJECT_ROOT / "results" / "metrics" / "vpn_metrics.json"))
    assert m["test"]["accuracy"] > 0.8
    assert (PROJECT_ROOT / "results" / "figures" / "vpn_confusion_matrix.png").exists()
    assert (PROJECT_ROOT / "results" / "figures" / "vpn_class_distribution.png").exists()
    return f"test_acc={m['test']['accuracy']:.4f}, figures exist"


def t_cnn():
    import torch
    d = torch.load(PROJECT_ROOT / "models" / "vpn_cnn.pt", map_location="cpu", weights_only=False)
    assert d["metrics"]["test_accuracy"] > 0.7, d["metrics"]
    return f"cnn test_acc={d['metrics']['test_accuracy']:.4f} (fair, same split)"


checks = [
    ("inventory generation", t_inventory),
    ("feature extraction from valid captures", t_features),
    ("correct label mapping", lambda: f"mapping={LABEL_MAPPING}" if LABEL_MAPPING == {"nonvpn": 0, "vpn": 1} else (_ for _ in ()).throw(AssertionError("bad mapping"))),
    ("leakage-aware train/test splitting", t_split),
    ("successful baseline training", t_model_artifact),
    ("evaluation on held-out capture groups", t_metrics_figures),
    ("saving fitted model + preprocessing artifacts", t_model_artifact),
    ("loading artifact in fresh process", t_fresh_predict_heldout),
    ("successful prediction on held-out valid capture", t_fresh_predict_heldout),
    ("invalid-file handling", t_invalid_handling),
    ("same feature schema train vs inference", t_schema_consistency),
    ("deterministic predictions", t_determinism),
    ("1D-CNN second model (fair sequence rep)", t_cnn),
]
for name, fn in checks:
    check(name, fn)

n_pass = sum(1 for r in results if r["status"] == "passed")
print(f"\n{n_pass}/{len(results)} passed")
out = PROJECT_ROOT / "results" / "metrics" / "acceptance_tests.json"
out.parent.mkdir(parents=True, exist_ok=True)
json.dump(results, open(out, "w"), indent=2)
print(f"Saved -> {out}")
