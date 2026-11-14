"""Finds wall and structure outlines in screenshots of the Odyssey Map Guide (opencv needed; NOT part of the app).

Run it in a folder of screenshots named like military_3.jpg (the guide at 1568x751, icons on). It writes ground.json: closed outlines in map
coordinates (the 1634x830 frame of maps/settlements/*.json). Automatic outlining is only clean on some bases (walled military ones); check the
result by eye before adding a 'ground' list to a map file.
"""
import cv2
import glob
import json
import os

import numpy as np
S=1.225
def extract(path):
    full=cv2.imread(path)
    im=full[34:708,0:1334].copy()
    hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
    H=hsv[...,0].astype(int)
    icon=((hsv[...,1]>190)&(hsv[...,2]>170)&((H<8)|(H>172)|((H>=95)&(H<=125))|((H>=28)&(H<=46)))).astype(np.uint8)
    icon=cv2.dilate(icon,np.ones((11,11),np.uint8))
    # white label text
    white=((hsv[...,1]<40)&(hsv[...,2]>235)).astype(np.uint8)
    lab=cv2.cvtColor(im,cv2.COLOR_BGR2LAB).astype(np.float32)
    small=cv2.resize(lab,(167,84),interpolation=cv2.INTER_AREA)
    bg=np.zeros_like(small)
    for c in range(3): bg[...,c]=cv2.medianBlur(small[...,c].astype(np.uint8),41).astype(np.float32)
    bg=cv2.resize(bg,(1334,674))
    diff=np.sqrt(((lab-bg)**2).sum(2))
    diff[icon>0]=0
    diff[cv2.dilate(white,np.ones((5,5),np.uint8))>0]=0
    diff=cv2.GaussianBlur(diff,(0,0),2.5)
    thr=np.percentile(diff,50)+2.2*np.std(diff)*0.6
    mask=(diff>thr).astype(np.uint8)*255
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((13,13),np.uint8))
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((7,7),np.uint8))
    cs,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    out=[]
    for c in cs:
        a=cv2.contourArea(c)
        if a<900 or a>220000: continue
        m=np.zeros(mask.shape,np.uint8); cv2.drawContours(m,[c],-1,255,-1)
        strength=float(diff[m>0].mean())/thr
        hull=cv2.contourArea(cv2.convexHull(c)); solid=a/max(hull,1)
        if strength<1.5 and a<5000: continue
        out.append((a,strength,cv2.approxPolyDP(c,4,True).reshape(-1,2)))
    out.sort(key=lambda t:-t[0]); out=out[:45]
    polys=[]
    for a,s,p in out:
        polys.append([[int(round(S*x)),int(round(S*(y+34)-38))] for x,y in p])
    return polys
if __name__=="__main__":
    res={}
    for f in sorted(glob.glob('*.jpg')):
        n=os.path.splitext(f)[0]; res[n]=extract(f); print(n,len(res[n]),sum(len(p) for p in res[n]))
    json.dump(res,open('ground.json','w'))
