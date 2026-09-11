from diag_common import *
import concurrent.futures
import math
import time
import download_weight as d

def main():
    d.URL='https://modelscope.cn/models/AI-ModelScope/mineworld/resolve/0dd5561ab317115831badc50e09a6ebe98693d0e/checkpoints/300M_16f.ckpt'
    d.SIZE=2178994204
    d.EXPECTED='ab3a10cdd18373b26e60debb70112f4a190ae56559f906829ffb94ad9fdce0ff'
    d.PARTS=ROOT/'weights/300m_parts'
    d.PARTS.mkdir(parents=True,exist_ok=True)
    final=ROOT/'weights/300M_16f.verified.ckpt'
    if final.exists():
        assert sha(final)==d.EXPECTED
        return
    started=time.monotonic()
    count=math.ceil(d.SIZE/d.CHUNK)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for n,k in enumerate(pool.map(d.get_part,range(count))):
            print('SECOND_MODEL_PART',k,n+1,count,round(time.monotonic()-started,1),flush=True)
    temp=final.with_suffix('.tmp')
    with temp.open('wb') as f:
        for k in range(count):
            with (d.PARTS/f'{k:03d}.part').open('rb') as g:
                for block in iter(lambda:g.read(8*1024*1024),b''):
                    f.write(block)
    assert temp.stat().st_size==d.SIZE and sha(temp)==d.EXPECTED
    temp.replace(final)
    save(ROOT/'weights/secondary_provenance.json',dict(model='300M_16f',url=d.URL,sha256=d.EXPECTED,bytes=d.SIZE,source='Pinned ModelScope mirror; official MineWorld config at existing source revision',weights_only_loading_required=True))
    print('SECOND_MODEL_HASH_VERIFIED',flush=True)

if __name__=='__main__':
    main()
