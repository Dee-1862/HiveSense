"""
Load and run the Vit4V Varroa video classifier (models/Vit4V_model.pth).

The checkpoint is a fine-tuned HuggingFace ViViT (google/vivit-b-16x2-kinetics400):
  * input : a 32-frame, 224x224 RGB clip of a bee passing the tunnel
  * output: a single logit -> sigmoid -> P(Varroa present)

We rebuild the architecture from config (NO weights downloaded) and load the
fine-tuned weights, stripping the 'module.model.' prefix left by DataParallel.

REQUIRES transformers==4.44.x: the checkpoint uses the older ViViT key names
(vivit.encoder.layer.N.attention.attention.query.*). transformers 5.x renamed these
(vivit.layers.N.attention.q_proj.*), so a 5.x load silently leaves the 12 encoder
layers RANDOM. load_model() below fails loudly if that happens.

Real evaluation needs actual bee clips (VD2 / BUT-2); none are on disk yet, so
`main()` runs a synthetic-clip smoke test that proves the model loads and runs.
"""

import os
import torch
from transformers import VivitConfig, VivitForVideoClassification

CKPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "models", "Vit4V_model.pth")
NUM_FRAMES = 32
IMAGE_SIZE = 224


def load_model(ckpt=CKPT, device="cpu"):
    """Rebuild the ViViT-B binary classifier and load the fine-tuned weights."""
    config = VivitConfig(
        image_size=IMAGE_SIZE,
        num_frames=NUM_FRAMES,
        tubelet_size=[2, 16, 16],
        hidden_size=768,
        num_hidden_layers=12,
        num_attention_heads=12,
        intermediate_size=3072,
        num_labels=1,                 # binary: single sigmoid logit
    )
    model = VivitForVideoClassification(config)

    raw = torch.load(ckpt, map_location=device)
    state = {k.replace("module.model.", ""): v for k, v in raw.items()}
    missing, unexpected = model.load_state_dict(state, strict=False)
    # A clean checkpoint loads with zero mismatches. Encoder-key mismatches mean a
    # transformers-version mismatch and a silently broken (random) model -> fail loud.
    if missing or unexpected:
        raise RuntimeError(
            f"Checkpoint did not load cleanly ({len(missing)} missing, "
            f"{len(unexpected)} unexpected keys). You almost certainly have the wrong "
            f"transformers version - pin transformers==4.44.2. "
            f"Example missing: {missing[:2]}  unexpected: {unexpected[:2]}"
        )
    return model.to(device).eval()


@torch.no_grad()
def predict_clip(model, clip, device="cpu"):
    """clip: tensor (num_frames, 3, H, W) or (B, num_frames, 3, H, W) in [0,1].
    Returns P(Varroa) per clip."""
    if clip.dim() == 4:
        clip = clip.unsqueeze(0)
    logits = model(pixel_values=clip.to(device)).logits   # (B, 1)
    return torch.sigmoid(logits).squeeze(-1).cpu()


# Fixed seeded random projection 768 -> EMBED_DIM. A Johnson-Lindenstrauss map: it
# preserves cosine geometry without any trained weights, so the "vision embedding" is
# an honest compression of the real ViViT CLS token, not a new learned head.
EMBED_DIM = 64
_PROJ = None


def _projection(in_dim=768, out_dim=EMBED_DIM, seed=0):
    global _PROJ
    if _PROJ is None:
        import numpy as np
        rng = np.random.default_rng(seed)
        _PROJ = (rng.standard_normal((in_dim, out_dim)) / (in_dim ** 0.5)).astype("float32")
    return _PROJ


@torch.no_grad()
def embed_clip(model, clip, device="cpu", out_dim=EMBED_DIM):
    """Real vision embedding: pool the ViViT encoder CLS token (768-d) over the clip and
    project to out_dim. clip: (num_frames,3,H,W) or (B,...). Returns a numpy float32 vector."""
    import numpy as np
    if clip.dim() == 4:
        clip = clip.unsqueeze(0)
    enc = model.vivit(pixel_values=clip.to(device))      # encoder only, no classifier head
    cls = enc.last_hidden_state[:, 0]                     # (B, 768)
    pooled = cls.mean(0).cpu().numpy().astype("float32")  # (768,)
    return (pooled @ _projection(pooled.shape[-1], out_dim)).astype(np.float32)


def main():
    print("loading Vit4V checkpoint...")
    model = load_model()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"loaded OK: {n_params/1e6:.1f}M params, ViViT-B, 1 output logit")

    # synthetic smoke test (random clip) -> proves the forward pass runs end to end
    dummy = torch.rand(2, NUM_FRAMES, 3, IMAGE_SIZE, IMAGE_SIZE)
    prob = predict_clip(model, dummy)
    print(f"smoke test on 2 random clips -> P(Varroa) = {prob.tolist()}")
    print("\nUSABLE: yes - the checkpoint loads and runs.")
    print("To TEST on real data you still need bee tunnel clips (VD2 / BUT-2);")
    print("none are on disk. Drop 32-frame 224x224 RGB clips in and call predict_clip().")


if __name__ == "__main__":
    main()
