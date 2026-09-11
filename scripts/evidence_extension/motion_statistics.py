from common import *
from statistics_core import summarize_motion

def main():
    cells=[]; inputs={}
    for p in sorted((ROOT/'motion/predictions').glob('*.json')):
        data=read(p);cells.extend(data['cells']);inputs[p.name]=sha(p)
    required={'MW_700M','PIXEL_CURRENT','PIXEL_HISTORY16','FRAME_DIFF16','FLOW16','VIDEOMAE_S','META_LINEAR','META_CUBIC','META_FAMILY','ORACLE_LAST','ORACLE_CV'}
    assert required<={r['model'] for r in cells}
    result=summarize_motion(cells)
    save(ROOT/'motion/statistics.json',dict(inputs=inputs,**result))
    print('MOTION_STATISTICS_COMPLETE',len(cells),flush=True)

if __name__=='__main__':main()
