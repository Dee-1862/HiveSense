"""
MSPB colony-strength (population) classifier.

Task: from aggregated audio features, predict whether a colony is large (frames of
bees > 20) or small (<= 20). MSPB's published baseline is an SVM at 65.8% balanced
accuracy; we train a RandomForest and report balanced accuracy against that number.

Validation is HIVE-HELD-OUT (GroupShuffleSplit on Hive ID): no hive appears in both
train and test, so the score reflects generalization to unseen colonies, not memorized
hive identity.
"""

import os
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import balanced_accuracy_score, confusion_matrix

from mspb_loader import build_population_dataset, feature_columns

BASELINE_BAL_ACC = 0.658  # MSPB paper SVM baseline
N_SPLITS = 5
TEST_FRAC = 0.30
SEED = 42
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "models", "rf_population.pkl")


def main():
    df = build_population_dataset()
    feats = feature_columns(df)
    X = df[feats].to_numpy(float)
    y = df["label"].to_numpy(int)
    groups = df["hive_id"].to_numpy()

    print(f"population dataset: {len(df)} samples - {df['hive_id'].nunique()} hives - "
          f"{len(feats)} features")
    print(f"label balance: large(>20)={int(y.sum())}  small(<=20)={int((1-y).sum())}")

    if len(np.unique(y)) < 2:
        print("\n[FLAG] Only one class present - cannot train. Not synthesizing labels.")
        return

    gss = GroupShuffleSplit(n_splits=N_SPLITS, test_size=TEST_FRAC, random_state=SEED)
    scores, last = [], None
    for fold, (tr, te) in enumerate(gss.split(X, y, groups), 1):
        if len(np.unique(y[tr])) < 2 or len(np.unique(y[te])) < 2:
            continue
        clf = RandomForestClassifier(n_estimators=300, max_depth=None,
                                     class_weight="balanced", random_state=SEED, n_jobs=-1)
        clf.fit(X[tr], y[tr])
        pred = clf.predict(X[te])
        ba = balanced_accuracy_score(y[te], pred)
        scores.append(ba)
        last = (y[te], pred)
        print(f"  fold {fold}: held-out hives={len(np.unique(groups[te]))}  "
              f"test n={len(te)}  balanced_acc={ba:.3f}")

    if not scores:
        print("\n[FLAG] No usable hive-held-out fold had both classes - too few labelled hives.")
        return

    print(f"\nHive-held-out balanced accuracy: {np.mean(scores):.3f} +/- {np.std(scores):.3f}")
    print(f"MSPB SVM baseline:               {BASELINE_BAL_ACC:.3f}")
    print("=> " + ("beats" if np.mean(scores) >= BASELINE_BAL_ACC else "below") + " baseline")
    print("\nConfusion matrix (last fold) [rows=true small/large, cols=pred]:")
    print(confusion_matrix(*last))

    # Fit the production model on ALL data and save it (the hive-held-out score above
    # is the honest performance estimate; the shipped model uses every labelled sample).
    final = RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                   random_state=SEED, n_jobs=-1).fit(X, y)
    joblib.dump({"model": final, "features": feats, "task": "population",
                 "label_meaning": {0: "small(<=20 FoB)", 1: "large(>20 FoB)"},
                 "cv_balanced_acc": float(np.mean(scores)),
                 "baseline": BASELINE_BAL_ACC}, MODEL_PATH)
    print(f"\nSaved production model -> {MODEL_PATH}")


if __name__ == "__main__":
    main()
