"""
LSB steganography: "unimodal packing" of a multimodal hive reading.

We hide the acoustic feature bytes inside the least-significant bits of a vision frame
(or a generated spectrogram-style carrier) and store the result as a SINGLE lossless
PNG. That one image now carries BOTH modalities, so Redis keeps ONE key per reading
instead of two.

Be honest about the win: steganography does NOT make Redis itself faster. What it buys
is one key + one round-trip + one allocation per multimodal reading instead of two,
lower aggregate per-key overhead, and an atomic multimodal read (you can never get the
image without its audio, or vice-versa). bench/redis_bench.py measures exactly that, and
reports the small decode CPU cost honestly.

Layout: [4-byte big-endian payload length][payload bits], one bit per RGB channel-byte.
"""

import io

import numpy as np
from PIL import Image

HEADER_BITS = 32  # 4-byte length prefix


def _to_rgb_array(image) -> np.ndarray:
    """Accept a PIL Image, numpy array, PNG bytes, or a file path -> uint8 RGB array."""
    if isinstance(image, (bytes, bytearray)):
        img = Image.open(io.BytesIO(bytes(image)))
    elif isinstance(image, np.ndarray):
        arr = image
        if arr.dtype != np.uint8:
            arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8) if arr.max() <= 1.0 \
                else arr.astype(np.uint8)
        img = Image.fromarray(arr)
    elif isinstance(image, str):
        img = Image.open(image)
    else:
        img = image  # assume PIL Image
    return np.array(img.convert("RGB"), dtype=np.uint8)


def capacity_bytes(image) -> int:
    """Max payload (bytes) a carrier can hold."""
    return (int(_to_rgb_array(image).size) - HEADER_BITS) // 8


def encode(image, payload: bytes) -> bytes:
    """Embed `payload` in the LSBs of `image`; return lossless PNG bytes."""
    arr = _to_rgb_array(image)
    flat = arr.reshape(-1).copy()
    data = len(payload).to_bytes(4, "big") + bytes(payload)
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    if bits.size > flat.size:
        raise ValueError(f"payload too big: needs {bits.size} channel-bytes, "
                         f"carrier has {flat.size} (use a larger carrier)")
    flat[:bits.size] = (flat[:bits.size] & 0xFE) | bits
    buf = io.BytesIO()
    Image.fromarray(flat.reshape(arr.shape), "RGB").save(buf, format="PNG")
    return buf.getvalue()


def decode(png_bytes) -> bytes:
    """Recover the payload embedded by encode()."""
    flat = _to_rgb_array(png_bytes).reshape(-1)
    n = int.from_bytes(np.packbits(flat[:HEADER_BITS] & 1).tobytes(), "big")
    total = HEADER_BITS + n * 8
    if total > flat.size:
        raise ValueError("declared payload length exceeds carrier capacity (corrupt blob)")
    return np.packbits(flat[HEADER_BITS:total] & 1).tobytes()


def solid_carrier(width: int = 64, height: int = 64, color=(58, 48, 30)) -> np.ndarray:
    """A small deterministic carrier frame for when no real bee frame is on hand.
    64x64 RGB holds ~1.5 KB - plenty for the 88-byte acoustic vector."""
    arr = np.empty((height, width, 3), dtype=np.uint8)
    arr[:, :] = color
    grad = np.linspace(0, 40, width, dtype=np.int16)
    arr[:, :, 1] = np.clip(arr[:, :, 1].astype(np.int16) + grad, 0, 255).astype(np.uint8)
    return arr
