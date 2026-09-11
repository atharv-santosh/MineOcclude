from common import *
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

PAPER=SOURCE/'evidence_extension_outputs/paper'

def export(fig,name):
    PAPER.mkdir(parents=True,exist_ok=True)
    assert not (PAPER/f'{name}.pdf').exists()
    fig.savefig(PAPER/f'{name}.pdf',metadata={'Author':'','Title':name.replace('_',' ')})
    fig.savefig(PAPER/f'{name}.png',dpi=250)
    plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('--central-only',action='store_true');a=p.parse_args()
    plt.rcParams.update({'font.family':'serif','font.serif':['STIXGeneral'],'mathtext.fontset':'stix','font.size':8,'axes.labelsize':8,'axes.titlesize':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'ps.fonttype':42})
    if not (PAPER/'transfer_opacity.pdf').exists():
        fig,axes=plt.subplots(1,2,figsize=(5.5,2.55),layout='constrained')
        matrix=[]
        for s in ['L0','L1','L2','L3','L4']:
            cells=read(ROOT/'transfer'/f'{s}.json')['cells']
            ids=sorted({r['identity'] for r in cells})
            matrix.append([np.mean([np.sqrt(np.mean([(r['prediction']-r['target'])**2 for r in cells if r['identity']==i and r['destination']==c])) for i in ids]) for c in ['L0','L1','L2','L3','L4']])
        matrix=np.array(matrix)
        im=axes[0].imshow(matrix,cmap='YlOrBr',norm=LogNorm(.08,8.))
        for row in range(5):
            for col in range(5):axes[0].text(col,row,f'{matrix[row,col]:.2f}',ha='center',va='center',fontsize=7,color='white' if matrix[row,col]>2 else '#222222')
        axes[0].set_xticks(range(5),['Air','White','Blue','Brown','Stone'],rotation=45,ha='right')
        axes[0].set_yticks(range(5),['Air','White','Blue','Brown','Stone'])
        axes[0].set_xlabel('Test condition');axes[0].set_ylabel('Training condition')
        axes[0].set_title('(a) Unchanged-decoder transfer',loc='left')
        fig.colorbar(im,ax=axes[0],shrink=.75,pad=.02,label='RMSE (blocks; log color)')
        levels=['A000','A025','A050','A075','A100'];x=np.arange(5)/4
        for model,label,color in [('OPACITY_MW','MineWorld, refit','#6a3d9a'),('OPACITY_PIXELS','History pixels, refit','#d95f02')]:
            results=read(ROOT/'central'/f'{model}_statistics.json')['results']
            rs=[next(r for r in results if r['source']==c and r['condition']==c) for c in levels]
            y=np.array([r['rmse'] for r in rs]);ci=np.array([r['rmse_ci'] for r in rs])
            axes[1].errorbar(x,y,yerr=np.maximum(0,np.stack([y-ci[:,0],ci[:,1]-y])),color=color,marker='o',markersize=3,capsize=2,lw=1,label=label)
        results=read(ROOT/'central/OPACITY_MW_statistics.json')['results']
        axes[1].plot(x,[next(r['rmse'] for r in results if r['source']=='A000' and r['condition']==c) for c in levels],color='#6a3d9a',ls='--',lw=1,label='MineWorld, air-trained')
        axes[1].set_xticks(x,['0','0.25','0.5','0.75','1'])
        axes[1].set_xlabel('Fixed-overlay opacity');axes[1].set_ylabel('RMSE (blocks)')
        axes[1].set_title('(b) Appearance-controlled overlay',loc='left')
        axes[1].legend(frameon=False,fontsize=7,loc='upper left');axes[1].grid(axis='y',color='.9',lw=.5)
        export(fig,'transfer_opacity')
    if a.central_only:return
    assert read(ROOT/'motion/validation.json')['status']=='PASS'
    stats=read(ROOT/'motion/statistics.json')['summaries']
    def get(model,c,lo=1,hi=10):return next(r for r in stats if r['model']==model and r['condition']==c and r['source']==('METADATA' if model.startswith(('META','ORACLE')) else c) and r['layout']=='pooled' and r['ages']==[lo,hi])['rmse']
    if not (PAPER/'matched_motion_results.pdf').exists():
        fig,axes=plt.subplots(1,2,figsize=(5.5,2.65),layout='constrained')
        models=['MW_700M','VIDEOMAE_S','PIXEL_HISTORY16','FRAME_DIFF16','FLOW16','META_CUBIC','META_FAMILY','ORACLE_CV']
        labels=['MineWorld','VideoMAE-S','History pixels','Frame differences','Optical flow','Direction + age','+ motion type','Oracle velocity']
        y=np.arange(len(models));rs=[get(m,'L4') for m in models];v=np.array([r['mean'] for r in rs]);ci=np.array([r['ci'] for r in rs])
        colors=['#6a3d9a','#238b45','#d95f02','#fdbb84','#969696','#525252','#252525','#9e9ac8']
        axes[0].barh(y,v,color=colors,height=.65)
        axes[0].errorbar(v,y,xerr=np.maximum(0,np.stack([v-ci[:,0],ci[:,1]-v])),fmt='none',ecolor='black',capsize=2,lw=.7)
        axes[0].set_yticks(y,labels);axes[0].invert_yaxis();axes[0].set_xlabel('RMSE (blocks)')
        axes[0].set_title('(a) Opaque, ages 1–10',loc='left')
        for model,label,color in [('MW_700M','MineWorld','#6a3d9a'),('VIDEOMAE_S','VideoMAE-S','#238b45'),('PIXEL_HISTORY16','History pixels','#d95f02'),('META_CUBIC','Direction + age','#525252')]:
            rs=[get(model,'L4',lo,hi) for lo,hi in [(1,10),(11,15),(16,19)]];v=np.array([r['mean'] for r in rs]);ci=np.array([r['ci'] for r in rs])
            axes[1].errorbar(range(3),v,yerr=np.maximum(0,np.stack([v-ci[:,0],ci[:,1]-v])),color=color,marker='o',markersize=3,capsize=2,lw=1,label=label)
        axes[1].set_xticks(range(3),['1–10','11–15','16–19']);axes[1].set_xlabel('Occlusion age');axes[1].set_ylabel('RMSE (blocks)');axes[1].set_title('(b) Available-history boundary',loc='left')
        axes[1].legend(frameon=False,fontsize=7)
        for ax in axes:ax.grid(axis='x' if ax is axes[0] else 'y',color='.9',lw=.5);ax.set_axisbelow(True)
        export(fig,'matched_motion_results')

if __name__=='__main__':main()
