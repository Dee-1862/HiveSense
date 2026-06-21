"""
MSPB acoustic Varroa classifier.

Task: from aggregated audio features, predict whether a colony is infested
(Nb varroa / 100 bees >= 3% economic threshold) or clear.

IMPORTANT HONESTY NOTE: in the MSPB D1 (summer) data, Varroa counts are very low -
when this was last checked, *zero* of ~100 inspections reached the 3% threshold, so
the binary label is single-class and a classifier cannot be trained. This script
DETECTS that and refuses, rather than fabricating positives or quietly lowering the
threshold. If/when a split has both classes, it trains a hive-held-out RandomForest
with class weighting and reports ROC-AUC + a confusion matrix.

Validation is HIVE-HELD-OUT (GroupShuffleSplit on Hive ID).
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, confusion_matrix, balanced_accuracy_score

from mspb_loader import build_varroa_dataset, feature_columns, VARROA_THRESHOLD

N_SPLITS = 5
TEST_FRAC = 0.30
SEED = 42


def main():
    df = build_varroa_dataset(threshold=VARROA_THRESHOLD)
    feats = feature_columns(df)
    X = df[feats].to_numpy(float)
    y = df["label"].to_numpy(int)
    groups = df["hive_id"].to_numpy()

    pos = int(y.sum())
    print(f"varroa dataset: {len(df)} samples - {df['hive_id'].nunique()} hives - "
          f"{len(feats)} features")
    print(f"threshold: {VARROA_THRESHOLD}%  ->  infested={pos}  clear={len(y) - pos}")
    print(f"raw varroa_pct range: {df['target_value'].min():.2f}-{df['target_value'].max():.2f}% "
          f"(median {df['target_value'].median():.2f}%)")

    if len(np.unique(y)) < 2:
        print(f"\n[FLAG] Single class at the {VARROA_THRESHOLD}% threshold "
              f"({pos} positives). Cannot train a Varroa classifier on this data.")
        print("       Options (your call - none fabricate data):")
        print("       1. Acoustic Varroa is not learnable from MSPB D1; keep mites vision-only.")
        print("       2. Add MSPB D2, or a dataset that actually has hives above 3%.")
        print("       3. Reframe as regression on varroa_pct, or a lower data-driven cutoff -")
        print("          but say so explicitly; it is no longer the 3% economic threshold.")
        return

    gss = GroupShuffleSplit(n_splits=N_SPLITS, test_size=TEST_FRAC, random_state=SEED)
    aucs, bals, last = [], [], None
    for fold, (tr, te) in enumerate(gss.split(X, y, groups), 1):
        if len(np.unique(y[tr])) < 2 or len(np.unique(y[te])) < 2:
            continue
        clf = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                     random_state=SEED, n_jobs=-1)
        clf.fit(X[tr], y[tr])
        prob = clf.predict_proba(X[te])[:, 1]
        pred = clf.predict(X[te])
        aucs.append(roc_auc_score(y[te], prob))
        bals.append(balanced_accuracy_score(y[te], pred))
        last = (y[te], pred)
        print(f"  fold {fold}: test n={len(te)}  ROC-AUC={aucs[-1]:.3f}  bal_acc={bals[-1]:.3f}")

    if not aucs:
        print("\n[FLAG] No hive-held-out fold had both classes in train and test "
              "(positives too sparse / concentrated in few hives). Not training.")
        return

    print(f"\nHive-held-out ROC-AUC: {np.mean(aucs):.3f} +/- {np.std(aucs):.3f}")
    print(f"Hive-held-out bal_acc: {np.mean(bals):.3f} +/- {np.std(bals):.3f}")
    print("(Exploratory only - sparse positives. Not comparable to the 0.874 AUC "
          "Abdollahi paper, which used a different dataset.)")
    print("\nConfusion matrix (last fold) [rows=true clear/infested, cols=pred]:")
    print(confusion_matrix(*last))


if __name__ == "__main__":
    main()
