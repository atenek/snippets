import numpy as np

SEED    = 0x43564341
SEEDH   = 0x43564348
MAXF  = 65536

KEY     = np.random.default_rng(SEED).integers(0, 256, size=MAXF, dtype=np.uint8)
KEY_HDR = np.random.default_rng(SEEDH).integers(0, 256, size=108, dtype=np.uint8)

def mask(d, seed = SEED):
    arr = np.frombuffer(d, dtype=np.uint8) if isinstance(d, (bytes, bytearray)) else np.asarray(d, dtype=np.uint8)
    n = len(arr)
    key = KEY[:n] if seed == SEED and n <= MAXF else np.random.default_rng(seed).integers(0, 256, size=n, dtype=np.uint8)
    return np.bitwise_xor(arr, key)

def mask_d(d, seed = SEED):
    n = len(d)
    key = KEY[:n] if seed == SEED and n <= MAXF else np.random.default_rng(seed).integers(0, 256, size=n, dtype=np.uint8)
    np.bitwise_xor(d, key, out=d)

def mask_h(d, salt: int = 0):
    out = d.copy()
    np.bitwise_xor(out[12:], KEY_HDR ^ np.uint8(salt), out=out[12:])
    return out