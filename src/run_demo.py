"""
Vit4V demo: classify a bee as INFESTED vs CLEAR from a VD2 tunnel clip.

IMPORTANT: Vit4V is NOT run on the raw frame. The official pipeline first *crops the
bee* out of each frame (background subtraction + largest-contour box, 224px), then runs
the model on contiguous 32-frame windows of those crops. Feeding the whole UHD frame
makes the bee a few pixels and the model says CLEAR - that was the earlier wrong result.

We therefore reuse the repo's own VideoSegmenter + FrameBuffer (cloned at
github/vit4v/src) so preprocessing matches training exactly. Label convention from the
repo: 1 = infested, so P(infested) = sigmoid(logit).

Usage:
  python src/run_demo.py --video dataset/vd2/varroa_infested/<clip>.mkv
  python src/run_demo.py --video <clip>.mkv --annotate out.mp4
  python src/run_demo.py --frames <dir>   # pre-cropped bee frames (VD2 frame dataset)

Requires transformers==4.44.2 (see vit4v_infer.py), opencv, and the cloned vit4v repo.
"""

import os
import sys
import glob
import argparse
import numpy as np
import torch
import cv2
from PIL import Image
from transformers import VivitImageProcessor

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_ROOT, "github", "vit4v", "src"))  # repo modules

from vit4v_infer import load_model, NUM_FRAMES
try:
    from lib.dataset.VideoSegmenter import VideoSegmenter  # type: ignore  # from cloned github/vit4v
    from lib.dataset.frame_buffer import FrameBuffer        # type: ignore
except ImportError as _e:
    raise SystemExit(
        "Could not import the vit4v segmenter. Clone the repo into github/vit4v:\n"
        "  git clone https://github.com/kernel-machine/vit4v github/vit4v\n"
        f"(import error: {_e})"
    )

_PROC = VivitImageProcessor()  # default Vivit preprocessing (matches the kinetics base)


def _segment_to_tensor(segment):
    """segment: list of 224x224 RGB frames -> pixel_values (1, NUM_FRAMES, 3, 224, 224)."""
    per = [_PROC(Image.fromarray(f).convert("RGB"), return_tensors="pt")["pixel_values"].squeeze(0)
           for f in segment]
    return torch.stack(per).permute(1, 0, 2, 3, 4)  # (1, T, 3, H, W)


@torch.no_grad()
def predict_video(model, video_path, threshold=0.5):
    """Return (per-segment probs, per-segment bools). Uses the repo's bee-cropping."""
    vs = VideoSegmenter(video_path, output_size=224)
    fb = FrameBuffer(NUM_FRAMES)
    for frame in vs.get_frames():                       # already a 224x224 bee crop (BGR)
        fb.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if len(fb) < NUM_FRAMES:
        return [], []                                   # no bee detected / clip too short
    probs = []
    for seg in fb.get_segments():
        logit = model(pixel_values=_segment_to_tensor(seg)).logits
        probs.append(torch.sigmoid(logit).item())
    preds = [p >= threshold for p in probs]
    return probs, preds


@torch.no_grad()
def predict_frames(model, frames_dir, threshold=0.5):
    """For pre-cropped bee frames (VD2 frame dataset): one 32-frame window, evenly sampled."""
    files = sorted(sum([glob.glob(os.path.join(frames_dir, e)) for e in ("*.jpg", "*.jpeg", "*.png")], []))
    if not files:
        raise RuntimeError(f"No images in {frames_dir}")
    idx = np.linspace(0, len(files) - 1, NUM_FRAMES).astype(int)
    seg = [cv2.cvtColor(cv2.imread(files[i]), cv2.COLOR_BGR2RGB) for i in idx]
    prob = torch.sigmoid(model(pixel_values=_segment_to_tensor(seg)).logits).item()
    return [prob], [prob >= threshold]


def _verdict(probs, preds):
    """Aggregate per-segment results into one video-level call."""
    if not preds:
        return "NO BEE DETECTED", None, 0
    frac = sum(preds) / len(preds)                      # fraction of windows infested
    label = "INFESTED" if frac >= 0.5 else "CLEAR"      # majority vote ("most common")
    return label, float(np.mean(probs)), len(preds)


@torch.no_grad()
def annotate_video(model, in_path, out_path, threshold=0.5):
    """Compute the video-level verdict, then write every frame with it burned in."""
    probs, preds = predict_video(model, in_path, threshold)
    label, mean_p, n = _verdict(probs, preds)
    color = (0, 0, 255) if label == "INFESTED" else (0, 180, 0)
    cap = cv2.VideoCapture(in_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    txt = f"{label}  p={mean_p:.2f}" if mean_p is not None else label
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        cv2.rectangle(fr, (0, 0), (w - 1, h - 1), color, 8)
        cv2.putText(fr, txt, (24, 70), cv2.FONT_HERSHEY_SIMPLEX, 2.0, color, 4, cv2.LINE_AA)
        writer.write(fr)
    cap.release(); writer.release()
    print(f"wrote annotated video -> {out_path}  ({txt}, {n} window(s))")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--video")
    g.add_argument("--frames")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--annotate", help="write an annotated output video (requires --video)")
    args = ap.parse_args()

    print("loading Vit4V model (transformers==4.44.2 required)...")
    model = load_model()

    if args.annotate:
        if not args.video:
            ap.error("--annotate requires --video")
        annotate_video(model, args.video, args.annotate, args.threshold)
        return

    if args.video:
        probs, preds = predict_video(model, args.video, args.threshold)
        src = args.video
    else:
        probs, preds = predict_frames(model, args.frames, args.threshold)
        src = args.frames

    label, mean_p, n = _verdict(probs, preds)
    print(f"\nsource : {src}")
    if n == 0:
        print("no bee segments detected (clip too short or segmenter found no bee).")
    else:
        print(f"windows: {n} | infested {sum(preds)}/{n} | mean P(Varroa)={mean_p:.3f}")
        print(f"VERDICT: {label}  (threshold {args.threshold})")


if __name__ == "__main__":
    main()
