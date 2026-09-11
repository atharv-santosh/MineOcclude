"""Pinned range-checked resumable download, verified before final assembly."""
import concurrent.futures
import math
import os
import sys
import time
import urllib.request
from audit_recovery import ROOT, sha

URL='https://modelscope.cn/models/AI-ModelScope/mineworld/resolve/0dd5561ab317115831badc50e09a6ebe98693d0e/checkpoints/700M_16f.ckpt'
SIZE=3798736924
EXPECTED='a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5'
CHUNK=128*1024*1024
PARTS=ROOT/'recovery_inputs/weights/main_parts'
NAME='700M_16f'
if '--vae' in sys.argv:
    URL='https://modelscope.cn/models/AI-ModelScope/mineworld/resolve/0dd5561ab317115831badc50e09a6ebe98693d0e/checkpoints/vae/vae.ckpt'
    SIZE=1657555486
    EXPECTED='370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab'
    PARTS=ROOT/'recovery_inputs/weights/vae_parts'
    NAME='vae'


def get_part(i):
    low=i*CHUNK
    high=min(SIZE,low+CHUNK)-1
    path=PARTS/f'{i:03d}.part'
    expected=high-low+1
    for attempt in range(5):
        have=path.stat().st_size if path.exists() else 0
        assert have<=expected
        if have==expected:
            return i
        request=urllib.request.Request(URL,headers={'Range':f'bytes={low+have}-{high}','User-Agent':'MineOcclude-artifact-recovery/1.0'})
        try:
            with urllib.request.urlopen(request,timeout=90) as response:
                assert response.status==206,response.status
                assert response.headers['Content-Range']==f'bytes {low+have}-{high}/{SIZE}',response.headers
                with path.open('ab') as output:
                    while data:=response.read(1024*1024):
                        output.write(data)
                assert path.stat().st_size==expected
            return i
        except Exception as error:
            print('PART_RETRY',i,attempt,type(error).__name__,str(error)[:160],flush=True)
            if attempt==4:
                raise
            time.sleep(2)


if __name__=='__main__':
    PARTS.mkdir(parents=True,exist_ok=True)
    count=math.ceil(SIZE/CHUNK)
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures=[pool.submit(get_part,i) for i in range(count)]
        for j,future in enumerate(concurrent.futures.as_completed(futures)):
            print('PART_DONE',future.result(),j+1,count,'seconds',round(time.perf_counter()-start,1),flush=True)
    final=PARTS.parent/f'{NAME}.verified.ckpt'
    temp=final.with_suffix('.tmp')
    with temp.open('wb') as output:
        for i in range(count):
            with (PARTS/f'{i:03d}.part').open('rb') as source:
                while data:=source.read(8*1024*1024):
                    output.write(data)
    assert temp.stat().st_size==SIZE and sha(temp)==EXPECTED
    temp.replace(final)
    print('PINNED_CHECKPOINT_VERIFIED',final,'seconds',round(time.perf_counter()-start,1),flush=True)
