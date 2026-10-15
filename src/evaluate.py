"""Evaluate saved VPN classifier on genuinely held-out capture groups."""
import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from common import PROJECT_ROOT, PROCESSED_DIR, MODELS_DIR, FEATURE_NAMES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(PROJECT_ROOT / "models" / "vpn_classifier.pkl"))
    ap.add_argument("--features", default=str(PROCESSED_DIR / "features_windows.csv"))
    ap.add_argument("--split", default=str(PROCESSED_DIR / "split_groups.json"))
    ap.add_argument("--metrics-dir", default=str(PROJECT_ROOT / "results" / "metrics"))
    ap.add_argument("--figures-dir", default=str(PROJECT_ROOT / "results" / "figures"))
    args = ap.parse_args()

    from sklearn.metrics import (accuracy_score, precision_recall_fscore_support,
                                 classification_report, confusion_matrix)

    t0 = time.time()
    with open(args.model, "rb") as f:
        artifact = pickle.load(f)
    pipe = artifact["pipeline"]
    assert list(artifact["feature_names"]) == FEATURE_NAMES, "feature schema mismatch"

    df = pd.read_csv(args.features)
    with open(args.split) as f:
        split = json.load(f)
    test_g = split["test_groups"]
    val_g = split.get("val_groups", [])
    train_g = split.get("train_groups", [])

    # verify no test group was in train
    overlap = set(test_g) & set(train_g)
    assert len(overlap) == 0, f"leakage: test groups in train: {overlap}"

    results = {}
    for name, glist in [("test", test_g), ("val", val_g), ("train", train_g)]:
        mask = df["group"].isin(glist).to_numpy()
        Xt = df.loc[mask, FEATURE_NAMES].to_numpy(dtype=float)
        yt = df.loc[mask, "vpn_label_id"].to_numpy(dtype=int)
        pred = pipe.predict(Xt)
        proba = pipe.predict_proba(Xt) if hasattr(pipe, "predict_proba") else None
        acc = float(accuracy_score(yt, pred))
        prec, rec, f1, _ = precision_recall_fscore_support(yt, pred, average="weighted", zero_division=0)
        prec_m, rec_m, f1_m, _ = precision_recall_fscore_support(yt, pred, average="macro", zero_division=0)
        cm = confusion_matrix(yt, pred).tolist()
        rep = classification_report(yt, pred, target_names=["nonvpn", "vpn"], output_dict=True, zero_division=0)
        results[name] = {
            "n_samples": int(len(yt)),
            "n_groups": int(len(glist)),
            "groups": sorted(glist),
            "class_distribution": {"nonvpn": int((yt == 0).sum()), "vpn": int((yt == 1).sum())},
            "accuracy": acc,
            "precision_weighted": float(prec), "recall_weighted": float(rec), "f1_weighted": float(f1),
            "precision_macro": float(prec_m), "recall_macro": float(rec_m), "f1_macro": float(f1_m),
            "confusion_matrix": cm,
            "classification_report": rep,
        }
        print(f"{name}: n={len(yt)} groups={len(glist)} acc={acc:.4f} f1w={f1:.4f}")

    results["meta"] = {
        "model": args.model,
        "model_version": artifact.get("model_version"),
        "task": artifact.get("task"),
        "feature_schema_ok": True,
        "test_train_overlap_groups": [],
        "eval_duration_sec": time.time() - t0,
        "limitations": ("Group-wise split: all windows of a capture stay in one split. "
                        "Large captures truncated to first 20000 packets; val/test use same rule. "
                        "Performance varies by application group (audio/video/chat/email)."),
    }

    mdir = Path(args.metrics_dir); mdir.mkdir(parents=True, exist_ok=True)
    fdir = Path(args.figures_dir); fdir.mkdir(parents=True, exist_ok=True)
    with open(mdir / "vpn_metrics.json", "w") as f:
        json.dump(results, f, indent=2)
    # also save classification report text
    df_test = df[df["group"].isin(test_g)]
    yt = df_test["vpn_label_id"].to_numpy()
    yp = pipe.predict(df_test[FEATURE_NAMES].to_numpy(dtype=float))
    with open(mdir / "vpn_classification_report.txt", "w") as f:
        f.write(classification_report(yt, yp, target_names=["nonvpn", "vpn"]))

    # figures (matplotlib, no seaborn dependency)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cm = np.array(results["test"]["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(["nonvpn", "vpn"]); ax.set_yticklabels(["nonvpn", "vpn"])
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_title("VPN classifier - test confusion matrix (held-out captures)")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(fdir / "vpn_confusion_matrix.png", dpi=150)
    plt.close(fig)

    # class distribution bar
    fig, ax = plt.subplots(figsize=(6, 3.5))
    labels = ["train", "val", "test"]
    nv = [results[k]["class_distribution"]["nonvpn"] for k in labels]
    vp = [results[k]["class_distribution"]["vpn"] for k in labels]
    x = np.arange(len(labels))
    ax.bar(x, nv, label="nonvpn")
    ax.bar(x, vp, bottom=nv, label="vpn")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("windows")
    ax.set_title("Class distribution per leakage-aware split")
    ax.legend()
    fig.tight_layout()
    fig.savefig(fdir / "vpn_class_distribution.png", dpi=150)
    plt.close(fig)

    print(f"\nSaved metrics -> {mdir / 'vpn_metrics.json'}")
    print(f"Saved figures -> {fdir}")


if __name__ == "__main__":
    main()
