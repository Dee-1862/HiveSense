"""
MSPB loader.

Loads the MSPB dataset (Multi-Sensor dataset with Phenotypic trait measurements
from honey Bees, Zenodo 11398835 / 8371700) and builds two supervised tables:

  - varroa_df      : audio-feature aggregates + binary Varroa label + Hive ID
  - population_df  : audio-feature aggregates + binary colony-strength label + Hive ID

Design rules (do not relax):
  * Labels are read straight from the phenotype workbook. We NEVER fabricate a label.
    If a required label column is absent the loader raises; if a thresholded label is
    single-class the *trainer* refuses (see train_*.py) rather than inventing positives.
  * The sensor table (audio features) and the phenotype workbook use different hive-id
    systems. They are joined on the verified key below, never blindly concatenated.
  * Only MSPB is used here. MSPB feature spaces must never be mixed with To-bee/UrBAN.

Verified facts (checked against the data on 2026-06):
  * Sensor hive id  = `tag_number` (6 digits, e.g. 202040). Stripping the leading
    "20" yields the phenotype "Hive ID" (= "Colony number Nectar", e.g. 2040).
    53/85 sensor tags map onto exactly the 53 known colonies; the other 32 tags are
    non-hive devices and are dropped.
  * 20 audio features = hive_power + 16 hz_* bands + audio_density + audio_density_ratio
    + density_variation. temperature/humidity are environmental, not part of the 20.
  * Varroa label  : "Phenotypic measurements" sheet, "Nb varroa / 100 bees" columns
    (two timepoints, each with its own preceding Date column). Binary: pct >= threshold.
  * Population lbl: "Evaluation N" sheets, "Number of frames covered by bees" sub-columns
    summed per (hive, date) -> frames of bees. Binary: fob > split (default 20).
"""

import os
import numpy as np
import pandas as pd

MSPB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset", "MSPB"
)

# The 20 audio features that are the model inputs.
AUDIO_FEATURES = [
    "hive_power",
    "hz_122.0703125", "hz_152.587890625", "hz_183.10546875", "hz_213.623046875",
    "hz_244.140625", "hz_274.658203125", "hz_305.17578125", "hz_335.693359375",
    "hz_366.2109375", "hz_396.728515625", "hz_427.24609375", "hz_457.763671875",
    "hz_488.28125", "hz_518.798828125", "hz_549.31640625", "hz_579.833984375",
    "audio_density", "audio_density_ratio", "density_variation",
]

VARROA_THRESHOLD = 3.0   # mites per 100 bees; economic treatment threshold
FOB_SPLIT = 20.0         # frames of bees; MSPB baseline small(<=20) vs large(>20)
WINDOW_DAYS = 3          # +/- days of sensor data aggregated around each inspection


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _excel_date(v):
    """Excel serial number OR real datetime -> pandas Timestamp (day resolution)."""
    if pd.isna(v):
        return pd.NaT
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (pd.Timestamp("1899-12-30") + pd.to_timedelta(float(v), unit="D")).normalize()
    return pd.to_datetime(v, errors="coerce").normalize()


def _nectar_id(tag_number):
    """Sensor tag_number (e.g. 202040) -> phenotype Hive ID (e.g. 2040). None if not a hive."""
    s = str(int(tag_number)) if pd.notna(tag_number) else ""
    if len(s) == 6 and s.startswith("20"):
        return int(s[2:])
    return None


# --------------------------------------------------------------------------- #
# sensor side (audio features)
# --------------------------------------------------------------------------- #
def load_sensor(dataset="D1"):
    """Load the per-reading sensor table, parsed and keyed by phenotype Hive ID.

    Returns a DataFrame with columns: hive_id, ts, + the 20 AUDIO_FEATURES,
    sorted by (hive_id, ts). Rows whose tag_number is not a known hive are dropped.
    """
    path = os.path.join(MSPB_DIR, f"{dataset}_sensor_data.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"MSPB sensor file not found: {path}")

    usecols = ["tag_number", "published_at"] + AUDIO_FEATURES
    df = pd.read_csv(path, usecols=usecols)

    df["hive_id"] = df["tag_number"].map(_nectar_id)
    df = df[df["hive_id"].notna()].copy()
    df["hive_id"] = df["hive_id"].astype(int)
    df["ts"] = pd.to_datetime(df["published_at"], utc=True, errors="coerce").dt.tz_localize(None)
    df = df.dropna(subset=["ts"])

    for c in AUDIO_FEATURES:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df[["hive_id", "ts"] + AUDIO_FEATURES].sort_values(["hive_id", "ts"])
    return df.reset_index(drop=True)


def _aggregate(window, deltas=True):
    """Aggregate a (time-sorted) window of sensor rows into one feature vector.

    mean of each feature; optionally + 1st-order and 2nd-order mean deltas
    (the MSPB population baseline uses mean + 1st/2nd-order deltas).
    """
    feats = {}
    mat = window[AUDIO_FEATURES].to_numpy(dtype=float)
    means = np.nanmean(mat, axis=0)
    for f, m in zip(AUDIO_FEATURES, means):
        feats[f"{f}__mean"] = m
    if deltas:
        d1 = np.diff(mat, axis=0)
        d2 = np.diff(mat, n=2, axis=0)
        d1m = np.nanmean(d1, axis=0) if d1.shape[0] else np.zeros(mat.shape[1])
        d2m = np.nanmean(d2, axis=0) if d2.shape[0] else np.zeros(mat.shape[1])
        for f, a, b in zip(AUDIO_FEATURES, d1m, d2m):
            feats[f"{f}__d1"] = a
            feats[f"{f}__d2"] = b
    return feats


def _join_features(labels_df, sensor_df, window_days=WINDOW_DAYS, deltas=True):
    """For each (hive_id, date) label row, aggregate sensor features in a +/-window.

    Rows with no sensor coverage in the window are dropped (never imputed).
    """
    win = pd.Timedelta(days=window_days)
    by_hive = {h: g for h, g in sensor_df.groupby("hive_id")}
    rows = []
    for _, lab in labels_df.iterrows():
        g = by_hive.get(int(lab["hive_id"]))
        if g is None:
            continue
        d = lab["date"]
        m = (g["ts"] >= d - win) & (g["ts"] <= d + win)
        window = g[m]
        if window.empty:
            continue
        feats = _aggregate(window, deltas=deltas)
        feats["hive_id"] = int(lab["hive_id"])
        feats["date"] = d
        feats["n_sensor_rows"] = int(window.shape[0])
        feats["target_value"] = lab["value"]
        feats["label"] = lab["label"]
        rows.append(feats)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# phenotype side (labels)
# --------------------------------------------------------------------------- #
def _load_phenotype_varroa(dataset="D1"):
    """Long table of (hive_id, date, varroa_pct) from 'Phenotypic measurements'."""
    path = os.path.join(MSPB_DIR, f"{dataset}_ant.xlsx")
    ph = pd.read_excel(path, sheet_name="Phenotypic measurements", header=1, engine="openpyxl")
    cols = list(ph.columns)
    if "Hive ID" not in cols:
        raise ValueError("MSPB phenotype sheet missing 'Hive ID' column - aborting (no synthesis).")
    varroa_idx = [i for i, c in enumerate(cols) if "varroa" in str(c).lower()]
    if not varroa_idx:
        raise ValueError("MSPB phenotype sheet has no 'Nb varroa / 100 bees' column - aborting.")
    recs = []
    for vi in varroa_idx:
        dcol = cols[vi - 1]  # the Date column immediately preceding each varroa column
        for _, r in ph.iterrows():
            hv = pd.to_numeric(r["Hive ID"], errors="coerce")
            val = pd.to_numeric(r[cols[vi]], errors="coerce")
            if pd.isna(hv) or pd.isna(val):
                continue
            recs.append({"hive_id": int(hv), "date": _excel_date(r[dcol]), "value": float(val)})
    return pd.DataFrame(recs).dropna(subset=["date"])


def _load_phenotype_population(dataset="D1"):
    """Long table of (hive_id, date, frames_of_bees) from the 'Evaluation N' sheets."""
    path = os.path.join(MSPB_DIR, f"{dataset}_ant.xlsx")
    xl = pd.ExcelFile(path, engine="openpyxl")
    recs = []
    for sh in [s for s in xl.sheet_names if s.startswith("Evaluation")]:
        raw = pd.read_excel(xl, sheet_name=sh, header=None)
        h0 = raw.iloc[0].tolist()
        hive_i = next(i for i, x in enumerate(h0) if str(x).strip() == "Hive ID")
        date_i = next(i for i, x in enumerate(h0) if "date" in str(x).lower())
        fs = next(i for i, x in enumerate(h0) if "frames covered" in str(x).lower())
        body = raw.iloc[2:]
        fob = body.iloc[:, fs:].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
        for hv, dt, f in zip(body.iloc[:, hive_i], body.iloc[:, date_i], fob):
            hv = pd.to_numeric(hv, errors="coerce")
            if pd.isna(hv) or pd.isna(f):
                continue
            recs.append({"hive_id": int(hv), "date": _excel_date(dt), "value": float(f)})
    return pd.DataFrame(recs).dropna(subset=["date"])


# --------------------------------------------------------------------------- #
# public builders
# --------------------------------------------------------------------------- #
def build_varroa_dataset(dataset="D1", threshold=VARROA_THRESHOLD, window_days=WINDOW_DAYS,
                         deltas=True, sensor=None):
    """Return varroa_df: aggregated audio features + binary label + Hive ID.

    label = 1 if Nb varroa / 100 bees >= `threshold` else 0. No positives are invented;
    if the data has none above threshold, that reality shows up in the label column.
    Pass a preloaded `sensor` frame to avoid re-reading the large CSV.
    """
    sensor = load_sensor(dataset) if sensor is None else sensor
    lab = _load_phenotype_varroa(dataset)
    lab["label"] = (lab["value"] >= threshold).astype(int)
    df = _join_features(lab, sensor, window_days=window_days, deltas=deltas)
    df.attrs["threshold"] = threshold
    df.attrs["task"] = "varroa"
    return df


def build_population_dataset(dataset="D1", split=FOB_SPLIT, window_days=WINDOW_DAYS,
                             deltas=True, sensor=None):
    """Return population_df: aggregated audio features + binary label + Hive ID.

    label = 1 (large) if frames of bees > `split` else 0 (small).
    Pass a preloaded `sensor` frame to avoid re-reading the large CSV.
    """
    sensor = load_sensor(dataset) if sensor is None else sensor
    lab = _load_phenotype_population(dataset)
    lab["label"] = (lab["value"] > split).astype(int)
    df = _join_features(lab, sensor, window_days=window_days, deltas=deltas)
    df.attrs["split"] = split
    df.attrs["task"] = "population"
    return df


def feature_columns(df):
    """The model-input columns in a built dataset (everything that isn't metadata/label)."""
    meta = {"hive_id", "date", "n_sensor_rows", "target_value", "label"}
    return [c for c in df.columns if c not in meta]


if __name__ == "__main__":
    for builder in (build_varroa_dataset, build_population_dataset):
        d = builder()
        task = d.attrs.get("task")
        n_feat = len(feature_columns(d))
        bal = d["label"].value_counts().to_dict()
        print(f"[{task}] rows={len(d)} hives={d['hive_id'].nunique()} "
              f"features={n_feat} label_balance={bal}")
