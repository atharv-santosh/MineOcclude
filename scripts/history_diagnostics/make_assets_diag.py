from diag_common import *
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=ROOT/'analysis'
PAPER=SOURCE/'history_diagnostic_outputs/paper'
LABELS={'MW_700M':'700M ridge','MW_300M':'300M ridge','MW_700M_MLP':'700M nonlinear','MW_300M_MLP':'300M nonlinear','PIXEL_CURRENT':'Current pixels','PIXEL_HISTORY16':'History pixels','IMAGE_TRACKER_CV':'Image tracker','DIRECTION_AGE':'Direction + age','TRAINING_MEAN':'Training mean','ORACLE_LAST_SEEN':'Oracle last-seen','ORACLE_CONSTANT_VELOCITY':'Oracle velocity'}
ORDER=list(LABELS)


def main():
    assert read(OUT/'independent_validation.json')['status']=='PASS'
    s=read(OUT/'statistics.json')
    summary={(r['model'],r['setting'],r['condition'],r['phase'],r['layout'],r['ages']):r for r in s['summaries']}
    PAPER.mkdir(parents=True,exist_ok=True)
    def value(m,c='L4',phase='correct',layout='pooled',ages='1-10',setting='native'):
        return summary[m,setting,c,phase,layout,ages]['rmse']
    plt.rcParams.update({'font.family':'serif','font.serif':['STIXGeneral'],'mathtext.fontset':'stix','font.size':9,'axes.labelsize':9,'axes.titlesize':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'ps.fonttype':42})
    fig,axes=plt.subplots(1,2,figsize=(6.6,2.6),gridspec_kw={'width_ratios':[1.15,1]},layout='constrained')
    models=['MW_700M','MW_700M_MLP','MW_300M','PIXEL_HISTORY16','IMAGE_TRACKER_CV','DIRECTION_AGE']
    means=np.array([value(m)['mean'] for m in models])
    ci=np.array([value(m)['ci95'] for m in models])
    colors=['#2166ac','#7b3294','#67a9cf','#d95f02','#1b9e77','#555555']
    axes[0].barh(np.arange(len(models)),means,color=colors,height=.6)
    axes[0].errorbar(means,np.arange(len(models)),xerr=np.maximum(0,np.stack([means-ci[:,0],ci[:,1]-means])),fmt='none',ecolor='#202020',capsize=2,elinewidth=.8)
    axes[0].set_yticks(np.arange(len(models)),[LABELS[m] for m in models]); axes[0].invert_yaxis()
    axes[0].set_xlabel('Mean identity RMSE (blocks)')
    axes[0].set_title('(a) Variable-speed held-out test',loc='left')
    for model,color in [('MW_700M','#2166ac'),('MW_300M','#67a9cf'),('PIXEL_HISTORY16','#d95f02')]:
        rows=[value(model,phase=p) for p in ['correct','swapped','removed']]
        y=np.array([r['mean'] for r in rows]); intervals=np.array([r['ci95'] for r in rows])
        axes[1].errorbar([0,1,2],y,yerr=np.maximum(0,np.stack([y-intervals[:,0],intervals[:,1]-y])),color=color,marker='o',markersize=4,linewidth=1.1,capsize=2,label=LABELS[model])
    axes[1].set_xticks([0,1,2],['Correct','Swapped','Removed'])
    axes[1].set_ylabel('Mean identity RMSE (blocks)')
    axes[1].set_title('(b) Current image held fixed',loc='left')
    axes[1].legend(frameon=False,fontsize=8,loc='best')
    for ax in axes:
        ax.grid(axis='x' if ax is axes[0] else 'y',color='.9',linewidth=.5)
        ax.set_axisbelow(True)
    fig.savefig(PAPER/'history_diagnostic_results.pdf',metadata={'Author':'','Title':'Held-out variable-speed history diagnostic'})
    fig.savefig(PAPER/'history_diagnostic_results.png',dpi=240)
    plt.close(fig)
    rows=read(ROOT/'roster.json')['identities']; by={r['identity']:r for r in rows}
    recipient=by['h26_layout_01_test_0_00']; donor=by[recipient['donor']]
    tr=recipient['target_model_frame_indices'][0]; td=donor['target_model_frame_indices'][0]
    fig,axes=plt.subplots(3,4,figsize=(6.6,3.1))
    provenance=[]
    for row,phase in enumerate(['Correct','Swapped','Removed']):
        for col,lag in enumerate([15,8,1,0]):
            source=recipient if phase!='Swapped' or lag==0 else donor
            frame=tr if phase=='Removed' else (tr if source is recipient else td)-lag
            path=ROOT/'captures'/f"{source['identity']}__L4"/'client/frames'/f'{frame:06d}.png'
            axes[row,col].imshow(Image.open(path).convert('RGB'))
            axes[row,col].set_xticks([]); axes[row,col].set_yticks([])
            for spine in axes[row,col].spines.values(): spine.set_visible(False)
            if row==0: axes[row,col].set_title(['First context image','Middle context image','Previous image','Current image'][col],fontsize=8)
            if col==0: axes[row,col].set_ylabel(phase,fontsize=9)
            provenance.append(dict(phase=phase,column=col,identity=source['identity'],frame=frame,sha256=sha(path)))
    fig.subplots_adjust(left=.08,right=.995,top=.93,bottom=.015,wspace=.025,hspace=.035)
    fig.savefig(PAPER/'history_intervention_inputs.pdf',metadata={'Author':'','Title':'Actual recorded input-history substitutions'})
    fig.savefig(PAPER/'history_intervention_inputs.png',dpi=200)
    plt.close(fig)
    save(OUT/'figure_provenance.json',dict(status='PASS',statistics_sha256=sha(OUT/'statistics.json'),actual_capture_panels=provenance,selection_rule='First predetermined layout-01 left-to-right slow test identity at age 1; no outcome-based image selection'))
    table=[]
    for layout,title in [('pooled','Pooled test identities'),('layout_01','Original layout'),('layout_04','Changed layout')]:
        table.append(r'\begin{table}[!htbp]\centering\small')
        table.append(r'\caption{'+title+r': mean identity RMSE in blocks. Air is summarized over ages 1--10. Stone columns retain the prespecified age bins. Each layout has 24 test identities; the pooled table has 48.}')
        table.append(r'\begin{tabular}{@{}lrrrrr@{}}\toprule Predictor & Air 1--10 & Stone 1--10 & 11--15 & 16--19 & Stone 1--19\\\midrule')
        for m in ORDER:
            vals=[value(m,'L0',layout=layout)['mean']]+[value(m,layout=layout,ages=b)['mean'] for b in ['1-10','11-15','16-19','1-19']]
            table.append(LABELS[m]+' & '+' & '.join(f'{v:.3f}' for v in vals)+r'\\')
        table.append(r'\bottomrule\end{tabular}\end{table}')
    ints={(r['model'],r['layout'],r['ages'],r['phase']):r for r in s['interventions']}
    table += [r'\begin{table}[!htbp]\centering\small',r'\caption{History interventions at ages 1--10, pooled over 48 test identities. Entries are intervened minus correct-history RMSE with 95\% reciprocal-donor-pair bootstrap intervals. Positive values indicate worse decoding after intervention.}',r'\begin{tabular}{@{}lrr@{}}\toprule Predictor & Swapped minus correct & Removed minus correct\\\midrule']
    for m in ['MW_700M','MW_300M','MW_700M_MLP','MW_300M_MLP','PIXEL_CURRENT','PIXEL_HISTORY16','IMAGE_TRACKER_CV']:
        vals=[ints[m,'pooled','1-10',p]['rmse_difference'] for p in ['swapped','removed']]
        table.append(LABELS[m]+' & '+' & '.join(f"${v['mean']:.3f}\;[{v['ci95'][0]:.3f},{v['ci95'][1]:.3f}]$" for v in vals)+r'\\')
    table.append(r'\bottomrule\end{tabular}\end{table}')
    table += [r'\begin{table}[!htbp]\centering\small',r'\caption{Geometry transfer at ages 1--10 on 24 destination test identities. Each cell gives air/stone RMSE. Calibration uses only six predesignated destination-training identities in air.}',r'\begin{tabular}{@{}lrrr@{}}\toprule Predictor & Frozen transfer & Visible calibration & Native fit\\\midrule']
    for m in ['MW_700M','MW_300M','PIXEL_CURRENT','PIXEL_HISTORY16']:
        values=[]
        for setting in ['frozen_transfer','visible_calibrated_transfer','native']:
            v=[value(m,c,layout='layout_04',setting=setting)['mean'] for c in ['L0','L4']]
            values.append(f'{v[0]:.3f} / {v[1]:.3f}')
        table.append(LABELS[m]+' & '+' & '.join(values)+r'\\')
    table.append(r'\bottomrule\end{tabular}\end{table}')
    table += [r'\begin{table}[!htbp]\centering\small',r'\caption{Swapped-history response, ages 1--10, pooled. Direction agreement is the fraction of target rows where the prediction change has the sign of donor-minus-recipient position, averaged over identities. A zero prediction change is not counted as agreement. All quantities describe the fixed probe, not a discovered circuit.}',r'\begin{tabular}{@{}lrrrr@{}}\toprule Predictor & Absolute shift & Agreement & Donor MAE & Recipient MAE\\\midrule']
    for r in s['history_responses']:
        if r['layout']=='pooled' and r['ages']=='1-10':
            vals=[r[k]['mean'] for k in ['absolute_prediction_shift','donor_direction_agreement','swapped_donor_mae','swapped_recipient_mae']]
            table.append(LABELS[r['model']]+' & '+' & '.join(f'{v:.3f}' for v in vals)+r'\\')
    table.append(r'\bottomrule\end{tabular}\end{table}')
    (PAPER/'diagnostic_tables.tex').write_text('\n'.join(table)+'\n')
    print('DIAGNOSTIC_ASSETS_WRITTEN',flush=True)


if __name__=='__main__':
    main()
