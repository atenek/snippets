from random import choices
def R(n=1): return ''.join(choices(cs1, k=n))

cs0='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
cs1='LT↓>mOAЧℲRИ3r&k95Жa7EMΣ$Яf8∇6KJe↑b<S2ꟻ4⅄ʁWt?Ю+dN1cP%XZɔⱯYП#ШЛC"0'
mn,ms,mc='"name"','"size"','"md5"'
S_= str.maketrans(cs0, cs1)
p,nl,sp,dh,h,r,x1,x2,x3,x4='+','\n',' ','─','\033[?25l','\033[H\033[J','┌','┐','└','┘'
be,b0=b'',b'\x00'
M1=1020
