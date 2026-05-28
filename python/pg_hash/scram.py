import numpy as np

SEED    = 0x43564341
SEEDH   = 0x43564348
MAXF  = 65536
HOFFSET = 12
HLEN    = 108
KEY     = np.random.default_rng(SEED).integers(0, 256, size=MAXF, dtype=np.uint8)
KEY_HDR = np.random.default_rng(SEEDH).integers(0, 256, size=HLEN, dtype=np.uint8)

def scram(data: bytes | np.ndarray, seed: int = SEED) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8) if isinstance(data, (bytes, bytearray)) else np.asarray(data, dtype=np.uint8)
    n = len(arr)
    key = KEY[:n] if seed == SEED and n <= MAXF else np.random.default_rng(seed).integers(0, 256, size=n, dtype=np.uint8)
    return np.bitwise_xor(arr, key)

def scram_inplace(arr: np.ndarray, seed: int = SEED) -> None:
    n = len(arr)
    key = KEY[:n] if seed == SEED and n <= MAXF else np.random.default_rng(seed).integers(0, 256, size=n, dtype=np.uint8)
    np.bitwise_xor(arr, key, out=arr)

def scramh(raw: np.ndarray, salt: int = 0) -> np.ndarray:
    out = raw.copy()
    np.bitwise_xor(out[HOFFSET:], KEY_HDR ^ np.uint8(salt), out=out[HOFFSET:])
    return out