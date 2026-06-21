"""
Optional REAL bound multimodal embedding via ImageBind.

ImageBind (Girdhar et al., CVPR 2023 - "ImageBind: One Embedding Space To Bind Them All",
arXiv 2305.05665) learns ONE aligned space across six modalities (image, audio, ...). An
image and its paired audio land near each other, which is what makes a *single bound vector*
the honest "unimodal" representation of a multimodal reading:

  - cross-modal retrieval from one query (find past states that look OR sound like this one),
  - embedding arithmetic (compose/subtract modality vectors to build a "varroa-stress"
    direction) - capabilities a concatenation of two separate vectors cannot provide.

This module is OPTIONAL and fully import-guarded: the fleet and the file/Redis stores run
without it. It is the real upgrade path from the lightweight early-fusion concat in
src/embedding.py. Install:

    pip install git+https://github.com/facebookresearch/ImageBind.git
    # downloads the imagebind_huge checkpoint on first use (~4.5 GB)

Honest caveat (state it, like we label the ViViT projection): ImageBind's audio encoder was
trained on general audio, not bee acoustics, so bee-domain alignment is approximate. It still
yields a shared cross-modal space out of the box, which concatenation never does.

Output: a 1024-d L2-normalised vector (ImageBind's embedding dim). NOTE this is a different
space/dimension from the 86-d early-fusion vector used in the live fleet, so it gets its own
Redis index when used (see the showcase notebook).
"""

import numpy as np

IMAGEBIND_DIM = 1024
_model = None
_device = "cpu"


def available() -> bool:
    """True if the imagebind package is importable."""
    try:
        import imagebind  # noqa: F401
        return True
    except Exception:
        return False


def _load():
    global _model
    if _model is None:
        import torch
        from imagebind.models import imagebind_model
        _model = imagebind_model.imagebind_huge(pretrained=True).eval().to(_device)
        _torch = torch  # noqa: F841
    return _model


def _l2(v):
    v = np.asarray(v, dtype="float32")
    return v / (np.linalg.norm(v) + 1e-9)


def embed(image_paths=None, audio_paths=None):
    """Bind real media into the shared space.

    Pass image_paths and/or audio_paths (lists). Returns a dict
    {modality: np.ndarray[1024]} for each provided modality. Because the space is shared,
    the vectors are directly comparable and composable across modalities.
    """
    if not available():
        raise RuntimeError("imagebind is not installed - see module docstring for the pip line.")
    import torch
    from imagebind.models.imagebind_model import ModalityType
    from imagebind import data as ib_data

    model = _load()
    inputs = {}
    if image_paths:
        inputs[ModalityType.VISION] = ib_data.load_and_transform_vision_data(image_paths, _device)
    if audio_paths:
        inputs[ModalityType.AUDIO] = ib_data.load_and_transform_audio_data(audio_paths, _device)
    if not inputs:
        raise ValueError("provide image_paths and/or audio_paths")

    with torch.no_grad():
        out = model(inputs)
    return {mod: _l2(out[mod].cpu().numpy()[0]) for mod in inputs}


def bind_reading(image_path, audio_path):
    """One bound vector for a multimodal reading: the mean of the (already-aligned) image and
    audio embeddings - a single 1024-d vector standing in for the whole reading. Because the
    space is shared this is a meaningful fusion, unlike concatenating unaligned halves."""
    e = embed(image_paths=[image_path], audio_paths=[audio_path])
    from imagebind.models.imagebind_model import ModalityType
    return _l2(e[ModalityType.VISION] + e[ModalityType.AUDIO])
