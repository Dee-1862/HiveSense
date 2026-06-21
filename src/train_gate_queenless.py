"""
Train and save the two To-bee acoustic models:

  1. Gate (bee / noBee)  - input-validity guard.
  2. Queenless           - queenright vs queenless.

Both use MFCC+SSD features (cached by tobee_loader) and a RandomForest. We report
BOTH within-hive (random split) and hive-held-out (GroupShuffleSplit) balanced
accuracy, because the gap between them is the honest signal: as the EDA notebook
shows, the queenless task collapses cross-hive (the label is confounded with colony
identity in this dataset). The shipped model is fit on all data, but the hive-held-out
score is the number you should trust / quote.
"""

import os
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, GroupShuffleSplit
from sklearn.metrics import balanced_accuracy_score

import tobee_loader as T

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
SEED = 0


def _rf():
    return RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                  random_state=SEED, n_jobs=-1)


def _within_hive(X, y, k=5):
    s = [balanced_accuracy_score(y[te], _rf().fit(X[tr], y[tr]).predict(X[te]))
         for tr, te in StratifiedKFold(k, shuffle=True, random_state=SEED).split(X, y)]
    return float(np.mean(s)), float(np.std(s))


def _hive_held_out(X, y, g, n=8):
    s = []
    for tr, te in GroupShuffleSplit(n, test_size=0.3, random_state=SEED).split(X, y, g):
        if len(np.unique(y[tr])) < 2 or len(np.unique(y[te])) < 2:
            continue
        s.append(balanced_accuracy_score(y[te], _rf().fit(X[tr], y[tr]).predict(X[te])))
    return (float(np.mean(s)), float(np.std(s)), len(s)) if s else (float("nan"), float("nan"), 0)


def _load_cache():
    gp = os.path.join(T.CACHE_DIR, "gate_features.csv")
    qp = os.path.join(T.CACHE_DIR, "queen_features.csv")
    if not (os.path.exists(gp) and os.path.exists(qp)):
        print("cache missing - extracting To-bee features (one-time)...")
        T.build_and_cache()
    return pd.read_csv(gp), pd.read_csv(qp)


def _train_one(df, task, label_meaning):
    feats = T.feature_columns(df)
    X = df[feats].fillna(0).to_numpy(float)
    y = df["label"].to_numpy(int)
    g = df["hive_id"].to_numpy()
    print(f"\n=== {task} ===")
    print(f"samples={len(df)} hives={df['hive_id'].nunique()} features={len(feats)} "
          f"balance={df['label'].value_counts().to_dict()}")
    wi = _within_hive(X, y)
    ho = _hive_held_out(X, y, g)
    print(f"within-hive   balanced acc: {wi[0]:.3f} +/- {wi[1]:.3f}")
    print(f"hive-held-out balanced acc: {ho[0]:.3f} +/- {ho[1]:.3f}  (n_folds={ho[2]})")
    if not np.isnan(ho[0]) and wi[0] - ho[0] > 0.2:
        print("[WARN] large within-vs-cross gap -> identity leakage; cross-hive score is the honest one.")

    out = os.path.join(MODELS_DIR, f"rf_{task}.pkl")
    final = _rf().fit(X, y)
    joblib.dump({"model": final, "features": feats, "task": task,
                 "label_meaning": label_meaning,
                 "within_hive_balanced_acc": wi[0],
                 "hive_held_out_balanced_acc": ho[0]}, out)
    print(f"saved -> {out}")


def main():
    gate, queen = _load_cache()
    _train_one(gate, "gate", {0: "noBee", 1: "bee"})
    _train_one(queen, "queenless", {0: "queenless", 1: "queenright"})


if __name__ == "__main__":
    main()
