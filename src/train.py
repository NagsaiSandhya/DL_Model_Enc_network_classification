"""Train primary VPN vs non-VPN Random Forest with leakage-aware group split."""
import argparse
import json
import time
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from common import (
    PROJECT_ROOT, PROCESSED_DIR, MODELS_DIR, FEATURE_NAMES, LABEL_MAPPING,
    INV_LABEL_MAPPING, RANDOM_SEED, MODEL_VERSION,
)


def group_split(df, seed=RANDOM_SEED, test_frac_groups=0.22, val_frac_groups=0.18):
    """Stratified group split: keep all windows of a capture in one split.

    Splits unique capture groups per class so both classes are covered
    in train/val/test. Returns (train_groups, val_groups, test_groups).
    """
    rng = np.random.RandomState(seed)
    groups = df[["group", "vpn_label"]].drop_duplicates()
    train_g, val_g, test_g = [], [], []
    for label in sorted(groups["vpn_label"].unique()):
        glist = sorted(groups[groups["vpn_label"] == label]["group"].tolist())
        rng.shuffle(glist)
        n = len(glist)
        n_test = max(2, int(round(n * test_frac_groups)))
        n_val = max(1, int(round(n * val_frac_groups)))
        # ensure at least 1 train group
        if n_test + n_val >= n:
            n_val = max(1, n - n_test - 1)
        test_g.extend(glist[:n_test])
        val_g.extend(glist[n_test:n_test + n_val])
        train_g.extend(glist[n_test + n_val:])
    return sorted(train_g), sorted(val_g), sorted(test_g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default=str(PROCESSED_DIR / "features_windows.csv"))
    ap.add_argument("--model-out", default=str(MODELS_DIR / "vpn_classifier.pkl"))
    ap.add_argument("--split-out", default=str(PROCESSED_DIR / "split_groups.json"))
    ap.add_argument("--n-estimators", type=int, default=200)
    ap.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = ap.parse_args()

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, classification_report

    t0 = time.time()
    df = pd.read_csv(args.features)
    X = df[FEATURE_NAMES].to_numpy(dtype=float)
    y = df["vpn_label_id"].to_numpy(dtype=int)
    groups = df["group"].to_numpy()

    train_g, val_g, test_g = group_split(df, seed=args.seed)
    train_mask = df["group"].isin(train_g).to_numpy()
    val_mask = df["group"].isin(val_g).to_numpy()
    test_mask = df["group"].isin(test_g).to_numpy()

    X_train, y_train = X[train_mask], y[train_mask]
    X_val, y_val = X[val_mask], y[val_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    # duplicate check (exact duplicate feature rows across splits)
    train_set = set(map(tuple, np.round(X_train, 6).tolist()))
    test_dups = sum(1 for r in np.round(X_test, 6).tolist() if tuple(r) in train_set)
    print(f"Groups: train={len(train_g)} val={len(val_g)} test={len(test_g)}")
    print(f" Train groups: {train_g}")
    print(f" Val groups:   {val_g}")
    print(f" Test groups:  {test_g}")
    print(f"Samples: train={len(X_train)} val={len(X_val)} test={len(X_test)}")
    print(f"Class dist train: {np.bincount(y_train, minlength=2)}, val: {np.bincount(y_val, minlength=2)}, test: {np.bincount(y_test, minlength=2)}")
    print(f"Exact duplicate test rows also in train: {test_dups}/{len(X_test)}")

    config = {
        "model": "RandomForestClassifier",
        "n_estimators": args.n_estimators,
        "max_depth": None,
        "min_samples_leaf": 2,
        "class_weight": "balanced",
        "random_state": args.seed,
        "n_jobs": -1,
        "preprocessing": "StandardScaler",
        "features": FEATURE_NAMES,
    }
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(
            n_estimators=args.n_estimators, max_depth=None,
            min_samples_leaf=2, class_weight="balanced",
            random_state=args.seed, n_jobs=-1)),
    ])
    fit_t0 = time.time()
    pipe.fit(X_train, y_train)
    fit_dur = time.time() - fit_t0

    def _report(name, Xt, yt):
        pred = pipe.predict(Xt)
        acc = accuracy_score(yt, pred)
        print(f"{name} accuracy: {acc:.4f}")
        print(classification_report(yt, pred, target_names=["nonvpn", "vpn"]))
        return acc, pred

    train_acc, _ = _report("Train", X_train, y_train)
    val_acc, _ = _report("Val", X_val, y_val)
    test_acc, test_pred = _report("Test", X_test, y_test)

    # dependency versions
    import sklearn, numpy, pandas as _pd, scipy
    deps = {"scikit-learn": sklearn.__version__, "numpy": numpy.__version__,
            "pandas": _pd.__version__, "scipy": scipy.__version__,
            "python": __import__("sys").version.split()[0]}
    try:
        import scapy
        deps["scapy"] = scapy.__version__
    except Exception:
        pass

    split_meta = {"train_groups": train_g, "val_groups": val_g, "test_groups": test_g,
                  "seed": args.seed, "rule": "stratified-by-vpn-label group split; all windows of a capture stay in one split"}
    with open(args.split_out, "w") as f:
        json.dump(split_meta, f, indent=2)

    artifact = {
        "model_version": MODEL_VERSION,
        "task": "vpn_vs_nonvpn",
        "pipeline": pipe,  # fitted scaler + estimator together
        "feature_names": FEATURE_NAMES,
        "label_mapping": LABEL_MAPPING,
        "config": config,
        "split": split_meta,
        "metrics": {"train_accuracy": train_acc, "val_accuracy": val_acc, "test_accuracy": test_acc,
                    "n_train": len(X_train), "n_val": len(X_val), "n_test": len(X_test)},
        "train_duration_sec": fit_dur,
        "total_duration_sec": time.time() - t0,
        "dependencies": deps,
        "notes": "Fitted preprocessing (StandardScaler) is inside pipeline. Inference must use pipeline.predict with FEATURE_NAMES order.",
    }
    out = Path(args.model_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(artifact, f)
    print(f"\nSaved model -> {out}")
    print(f"Saved split -> {args.split_out}")
    print(f"Fit duration: {fit_dur:.1f}s, total: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
