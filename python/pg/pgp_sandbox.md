import sys
import hashlib
from pgc import C
from pgi import pz
from pgd import M1,mn,ms,mc,be,h,r,nl

class P:
    def __init__(self, f, id): self.f, self.id = f, id

    @property
    def m(self):
        with open(self.f, "rb") as f: h = hashlib.md5(f.read()).hexdigest()
        return f'{{{mn}:"{self.f.name}",{ms}:{self.f.stat().st_size},{mc}:"{h}"}}'.encode()

    def cs(self, pre: int | None = None):
        if pre is None or pre < 4: pre = 4
        for n in range(-pre, 0): yield C(n, self)
        yield C(0, self, self.m)
        with open(self.f, "rb") as f:
            for n, x in enumerate(iter(lambda: f.read(M1), be), 1):
                yield C(n, self, x)

    @property
    def t(self): return self.f.stat().st_size // M1 + 1

    def p(self, pre=12, d=240):
        print(h, r)
        for c in self.cs(pre=pre):
            print(r, c.mpg())
            sys.stdout.flush()
            pz(d/M1)
        print(2*nl)
