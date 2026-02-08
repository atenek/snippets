from pgi import rsde, rshe, cs, ura, es
from pgd import cs1,M1,sp,x1,x2,x3,x4,dh,p,nl,R,be,b0


class C:
    def __init__(self, num, fpg, bd=None):
        self.fpg, self.num, self.bd  = fpg, num, bd or be
        bdp = self.bd + ura(M1 - len(self.bd))
        self.data_b64cv_str = ''.join(es(rsde(bdp[204 * n:204 * (n + 1)])) for n in range(5))

    @property
    def csh(self):
        if self.num in (-3, -2):
            return 76*sp
        else:
            return f"{26*sp}{self.num:06}{sp}{self.fpg.t:06}{sp}{self.fpg.id:8}{26 * sp}"

    @property
    def ch(self):
        if self.num <= -4:
            return f"{x1}{dh}{R(72)}{dh}{x2}"
        elif self.num <= -3:
            return 76*sp
        elif self.num == -2:
            return f"{x1}{74*dh}{x2}"
        elif self.num == -1:
            return f"{x1}{dh}{72*p}{dh}{x2}"
        else:
            hdb = bytearray(ura(36))
            hdb[0:4], hdb[4:8]  = self.num.to_bytes(4, 'little'), self.fpg.t.to_bytes(4, 'little')
            hdb[8:16], hdb[16:20] = self.fpg.id.encode()[:8].ljust(8, b0), (cs(self.bd) & 0xffffffff).to_bytes(4, 'little')
            hdb[20:22] = len(self.bd).to_bytes(2, 'little')
            return f"{x1}{dh}{es(rshe(hdb))}{dh}{x2}"

    @property
    def cb(self):
        if self.num <= -4:
            return '\n'.join((f"{R(76)}" for _ in range(20)))
        elif self.num == -3:
            return f"{3*sp}O{R(68)}O{3 * sp}{nl}{2 * sp}{R(72)}{2 * sp}{nl}{nl.join((R(76) for _ in range(16)))}{nl}{2*sp}{R(72)}{2 * sp}{nl}{3 * sp}O{R(68)}O{3*sp}"
        elif self.num == -2:
            return (f"{76*p}{nl}"*20)[:-1]
        elif self.num == -1:
            return (f"{5*sp}{cs1+'='}{6*sp}{nl}"*20)[:-1]
        else:
            return '\n'.join(self.data_b64cv_str[i:i+76] for i in range(0, len(self.data_b64cv_str), 76))

    @property
    def cf(self):
        if self.num <= -4:
            return f"{x3}{dh}{R(72)}{dh}{x4}"
        elif self.num == -3:
            return 76*sp
        elif self.num == -2:
            return f"{x3}{74*dh}{x4}"
        else:
            return f"{x3}{dh}{R(72)}{dh}{x4}"

    def mpg(self, lm=12, tm=3): return f"{tm*nl}{lm*sp}{self.pg.replace(nl,f'{nl}{sp*lm}')}"

    @property
    def pg(self): return f"{self.csh}{nl}{self.ch}{nl}{self.cb}{nl}{self.cf}"
