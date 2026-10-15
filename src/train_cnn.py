"""Small 1D-CNN on genuine packet sequences (leakage-aware split).

Input per window: ordered (50, 5) sequence [pkt_len, iat, direction,
is_tcp, is_udp] from data/processed/features_sequences.npz.
This is a valid sequential representation (ordered packet series),
not arbitrary tabular features fed to a CNN.

Uses the SAME group split as the Random Forest (split_groups.json)
for a fair comparison. Normalization fitted on TRAIN only.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from common import PROJECT_ROOT, PROCESSED_DIR, MODELS_DIR, RANDOM_SEED, SEQ_LEN


class TinyCNN:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default=str(PROCESSED_DIR / "features_sequences.npz"))
    ap.add_argument("--split", default=str(PROCESSED_DIR / "split_groups.json"))
    ap.add_argument("--out", default=str(MODELS_DIR / "vpn_cnn.pt"))
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = ap.parse_args()

    import torch
    import torch.nn as nn
    from torch.utils.data import TensorDataset, DataLoader

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    t0 = time.time()
    data = np.load(args.npz, allow_pickle=True)
    X, y, groups = data["X"].astype(np.float32), data["y"].astype(np.float32), data["groups"].astype(str)
    with open(args.split) as f:
        split = json.load(f)
    train_g, val_g, test_g = split["train_groups"], split["val_groups"], split["test_groups"]

    def mask(glist):
        return np.isin(groups, np.array(glist))

    Xtr, ytr = X[mask(train_g)], y[mask(train_g)]
    Xva, yva = X[mask(val_g)], y[mask(val_g)]
    Xte, yte = X[mask(test_g)], y[mask(test_g)]
    print(f"Seq shapes: train={Xtr.shape} val={Xva.shape} test={Xte.shape}")

    # normalize pkt_len (ch0) and iat (ch1) with train-only stats; direction/is_tcp/is_udp untouched
    mu_len, sd_len = float(Xtr[:, :, 0].mean()), float(Xtr[:, :, 0].std() + 1e-6)
    mu_iat, sd_iat = float(Xtr[:, :, 1].mean()), float(Xtr[:, :, 1].std() + 1e-6)

    def norm(a):
        b = a.copy()
        b[:, :, 0] = (b[:, :, 0] - mu_len) / sd_len
        b[:, :, 1] = (b[:, :, 1] - mu_iat) / sd_iat
        return b

    Xtr, Xva, Xte = norm(Xtr), norm(Xva), norm(Xte)

    class CNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv1d(5, 32, kernel_size=5, padding=2), nn.ReLU(), nn.MaxPool1d(2),
                nn.Conv1d(32, 64, kernel_size=3, padding=1), nn.ReLU(),
                nn.AdaptiveMaxPool1d(1),
            )
            self.fc = nn.Sequential(
                nn.Flatten(), nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(64, 1),
            )

        def forward(self, x):
            # x: (B, 50, 5) -> (B, 5, 50)
            x = x.transpose(1, 2)
            return self.fc(self.net(x)).squeeze(1)

    device = torch.device("cpu")
    model = CNN().to(device)
    # class imbalance: pos_weight from train
    n_pos = float((ytr == 1).sum())
    n_neg = float((ytr == 0).sum())
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)], device=device)
    crit = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)

    def batches(Xa, ya, shuffle):
        ds = TensorDataset(torch.from_numpy(Xa), torch.from_numpy(ya))
        return DataLoader(ds, batch_size=args.batch, shuffle=shuffle)

    best_val, best_state, patience, wait = 0.0, None, 4, 0
    for ep in range(1, args.epochs + 1):
        model.train()
        tot = 0.0
        for xb, yb in batches(Xtr, ytr, True):
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = crit(model(xb), yb)
            loss.backward()
            opt.step()
            tot += float(loss) * len(xb)
        # val acc
        model.eval()
        with torch.no_grad():
            pv = (torch.sigmoid(model(torch.from_numpy(Xva).to(device))) > 0.5).cpu().numpy().astype(int)
            vacc = float((pv == yva.astype(int)).mean())
        print(f"epoch {ep}: loss={tot/len(Xtr):.4f} val_acc={vacc:.4f}", flush=True)
        if vacc > best_val:
            best_val, wait = vacc, 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                print(f"early stop at epoch {ep}")
                break
    if best_state is not None:
        model.load_state_dict(best_state)

    def acc(Xa, ya):
        model.eval()
        with torch.no_grad():
            p = (torch.sigmoid(model(torch.from_numpy(Xa).to(device))) > 0.5).cpu().numpy().astype(int)
        return float((p == ya.astype(int)).mean()), p

    tracc, _ = acc(Xtr, ytr)
    vaacc, _ = acc(Xva, yva)
    teacc, tep = acc(Xte, yte)
    print(f"CNN train={tracc:.4f} val={vaacc:.4f} test={teacc:.4f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "arch": "Conv1d(5->32,k5)/MaxPool/Conv1d(32->64,k3)/AdaptiveMaxPool/Linear(64->64->1)",
        "seq_len": SEQ_LEN, "channels": ["pkt_len", "iat", "direction", "is_tcp", "is_udp"],
        "norm": {"mu_len": mu_len, "sd_len": sd_len, "mu_iat": mu_iat, "sd_iat": sd_iat},
        "label_mapping": {"nonvpn": 0, "vpn": 1},
        "split": {"train_groups": train_g, "val_groups": val_g, "test_groups": test_g},
        "metrics": {"train_accuracy": tracc, "val_accuracy": vaacc, "test_accuracy": teacc},
        "epochs": args.epochs, "seed": args.seed,
        "model_version": "1.0.0", "task": "vpn_vs_nonvpn",
        "train_duration_sec": time.time() - t0,
    }, out)
    # metrics json
    mdir = PROJECT_ROOT / "results" / "metrics"
    mdir.mkdir(parents=True, exist_ok=True)
    with open(mdir / "vpn_cnn_metrics.json", "w") as f:
        json.dump({"train_accuracy": tracc, "val_accuracy": vaacc, "test_accuracy": teacc,
                   "best_val_accuracy": best_val, "epochs": args.epochs,
                   "comparison_note": "Same leakage-aware group split as Random Forest; RF test=0.9634."}, f, indent=2)
    print(f"Saved CNN -> {out} (duration {time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
