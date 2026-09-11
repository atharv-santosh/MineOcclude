"""Deterministic publication figures from predictions and actual capture pixels."""
from pathlib import Path
import argparse
import hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
from audit_recovery import ROOT,OUT,PKG,read,save,sha

plt.rcParams.update({'font.family':'serif','font.serif':['STIXGeneral'],
 'mathtext.fontset':'cm','font.size':9,'axes.titlesize':10,'axes.labelsize':9,
 'legend.fontsize':8,'xtick.labelsize':8,'ytick.labelsize':8,
 'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,
 'savefig.dpi':300,'axes.linewidth':.7})
COLORS={'MW_RGB_L19':'#23678a','PIXEL_CURRENT':'#aa7046','PIXEL_HISTORY16':'#62914a','MW_BGR_L19':'#986794'}
LABELS={'MW_RGB_L19':'MineWorld, RGB (16 pairs)','PIXEL_CURRENT':'Pixels (current frame)',
 'PIXEL_HISTORY16':'Pixels (16-frame history)','MW_BGR_L19':'MineWorld, BGR replay'}
DEST=OUT/'paper'

def export(fig,name):
    DEST.mkdir(parents=True,exist_ok=True)
    fig.savefig(DEST/f'{name}.pdf',bbox_inches='tight',metadata={'CreationDate':None,'ModDate':None})
    fig.savefig(DEST/f'{name}.png',bbox_inches='tight')
    plt.close(fig)

def captures():
    index=read(PKG/'cohort/CAPTURE_INDEX.json')['captures']
    names=['Air','White glass','Blue glass','Brown glass','Stone']
    fig,axes=plt.subplots(1,5,figsize=(6.8,1.05))
    provenance=[]
    for j,ax in enumerate(axes):
        unit=f'e3_t01__L{j}'
        frame=index[unit]['target_model_frame_indices'][9]
        path=ROOT/'recovery_inputs/corpus/captures'/unit/'raw/frames'/f'{frame:06d}.png'
        with Image.open(path) as image:
            ax.imshow(np.asarray(image.convert('RGB')))
        ax.set_title(f'L{j}: {names[j]}',pad=4)
        ax.axis('off')
        provenance.append({'unit':unit,'row_index':9,'frame':frame,'sha256':sha(path)})
    fig.subplots_adjust(left=0,right=1,bottom=0,top=.78,wspace=.06)
    export(fig,'matched_captures')
    save(OUT/'figure_capture_provenance.json',provenance)

def results():
    data=read(OUT/'summary.json')
    s=data['summary']
    fig,axes=plt.subplots(1,2,figsize=(6.8,2.5),gridspec_kw={'width_ratios':[1.2,1]})
    for model in ('MW_RGB_L19','PIXEL_CURRENT','PIXEL_HISTORY16'):
        values=[s[model][f'L{k}']['rmse'] for k in range(5)]
        mean=np.array([v['mean'] for v in values])
        err=np.array([[v['mean']-v['ci_low'] for v in values],[v['ci_high']-v['mean'] for v in values]])
        axes[0].errorbar(range(5),mean,yerr=err,label=LABELS[model],color=COLORS[model],marker='o',ms=3,lw=1.2,capsize=2)
    axes[0].set_yscale('log')
    axes[0].set_xticks(range(5),['Air','White','Blue','Brown','Stone'])
    axes[0].set_ylabel('Mean identity RMSE (blocks; log scale)')
    axes[0].set_title('(a) Evidence ladder',loc='left')
    axes[0].grid(axis='y',alpha=.18)
    models=['MW_RGB_L19','PIXEL_HISTORY16','PIXEL_CURRENT','LEGACY_TIME_ONLY','LEGACY_CONSTANT_VELOCITY','LEGACY_LAST_SEEN']
    names=['MineWorld RGB','16-frame pixels','Current pixels','Direction + age','Oracle velocity','Oracle last-seen']
    for j,m in enumerate(models):
        v=s[m]['L4']['rmse']
        axes[1].errorbar(v['mean'],j,xerr=[[v['mean']-v['ci_low']],[v['ci_high']-v['mean']]],fmt='o',color=COLORS.get(m,'#777777'),ms=4,capsize=2)
    axes[1].set_yticks(range(len(models)),names)
    axes[1].invert_yaxis()
    axes[1].set_xlabel('Mean identity RMSE (blocks)')
    axes[1].set_title('(b) Opaque-condition comparators',loc='left')
    axes[1].grid(axis='x',alpha=.18)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,-.03),ncol=3,frameon=False)
    fig.subplots_adjust(left=.085,right=.99,bottom=.24,top=.87,wspace=.72)
    export(fig,'rgb_evidence_results')

    fig,axes=plt.subplots(1,2,figsize=(6.8,2.45))
    for model in ('MW_RGB_L19','MW_BGR_L19','PIXEL_HISTORY16','PIXEL_CURRENT'):
        rows=[]
        for path in sorted((OUT/'predictions').glob(f'{model}__L4.json')):
            rows.extend(read(path)['cells'])
        err=np.array([[abs(r['prediction']-r['target']) for r in sorted(rows,key=lambda r:(r['identity'],r['row_index']))]]).reshape(25,19)
        # One row per identity at an exact age: identity RMSE is absolute error.
        axes[0].plot(range(1,20),err.mean(axis=0),label=LABELS[model],color=COLORS[model],lw=1.2)
    axes[0].axvspan(15.5,19.5,color='#eeeeee',zorder=-2)
    axes[0].axvline(15.5,color='#777777',ls='--',lw=.8)
    axes[0].set_xlim(1,19)
    axes[0].set_xticks([1,5,10,15,19])
    axes[0].set_xlabel('Age since last non-full-occlusion row')
    axes[0].set_ylabel('Mean identity absolute error (blocks)')
    axes[0].set_title('(a) Stone: error and available history',loc='left')
    axes[0].grid(axis='y',alpha=.18)
    for cond,offset,color,label in [('L0',-.08,'#62914a','Air'),('L4',.08,'#23678a','Stone')]:
        for k,pairs in enumerate((1,8,16)):
            m='MW_RGB_L19'+(f'_CTX{pairs}' if pairs!=16 else '')
            v=s[m][cond]['rmse']
            axes[1].errorbar(k+offset,v['mean'],yerr=[[v['mean']-v['ci_low']],[v['ci_high']-v['mean']]],fmt='o',ms=4,capsize=3,color=color,label=label if k==0 else None)
    axes[1].set_xticks(range(3),['1 pair','8 pairs','16 pairs'])
    axes[1].set_ylabel('Mean identity RMSE (blocks)')
    axes[1].set_title('(b) Native reset-window length',loc='left')
    axes[1].legend(frameon=False)
    axes[1].grid(axis='y',alpha=.18)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,-.08),ncol=2,frameon=False)
    fig.subplots_adjust(left=.085,right=.99,bottom=.28,top=.87,wspace=.4)
    export(fig,'rgb_history_results')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--captures-only',action='store_true')
    args=parser.parse_args()
    captures()
    if not args.captures_only:
        results()
