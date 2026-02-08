import os
from base64 import b64decode, b64encode
from reedsolo import RSCodec
import time
import zlib
from pgd import S_

ura,pz,sd,se,cs=os.urandom,time.sleep,b64decode,b64encode,zlib.crc32
rshe,rsde = RSCodec(18,54).encode, RSCodec(24,228).encode
es = lambda x: se(x).decode().translate(S_)
