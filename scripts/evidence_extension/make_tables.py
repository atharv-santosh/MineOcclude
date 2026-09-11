from common import *

PAPER=SOURCE/'evidence_extension_outputs/paper'
LABELS={'MW_700M':'MineWorld','PIXEL_CURRENT':'Current pixels','PIXEL_HISTORY16':'History pixels','FRAME_DIFF16':'Frame differences','FLOW16':'Optical flow','VIDEOMAE_S':'VideoMAE-S','META_LINEAR':'Linear direction/age','META_CUBIC':'Cubic direction/age','META_FAMILY':'Plus motion type','ORACLE_LAST':'Oracle last position','ORACLE_CV':'Oracle velocity'}

def table(caption,label,headers,rows):
    return '\n'.join([r'\begin{table}[!htbp]',r'\centering\small',r'\caption{'+caption+'}',r'\label{'+label+'}',r'\begin{tabular}{@{}l'+'r'*(len(headers)-1)+r'@{}}',r'\toprule',' & '.join(headers)+r'\\',r'\midrule',*[' & '.join(row)+r'\\' for row in rows],r'\bottomrule',r'\end{tabular}',r'\end{table}',''])

def main():
    stats=read(ROOT/'motion/statistics.json')
    text=[r'\section{Complete evidence-extension results}',r'\label{app:extension-results}']
    histories=[r for r in read(ROOT/'motion/final_data_audit.json')['visible_history_by_identity'] if r['partition']=='test']
    assert len(histories)==128
    history_rows=[]
    for lo,hi in [(1,10),(11,15),(16,19)]:
        counts=[n for r in histories for n in r['visible_prior_counts'][lo-1:hi]]
        history_rows.append([f'{lo}--{hi}',str(len(counts)),f'{100*sum(n>0 for n in counts)/len(counts):.1f}\\%',f'{sum(counts)/len(counts):.2f}',f'{min(counts)}--{max(counts)}'])
    text.append(table('Observed input-history audit of the 128 held-out motion variants in stone. A prior frame is counted when the fixed sheep-color detector finds more than 20 sheep-colored pixels. These descriptive input counts do not establish position localizability and are not independent statistical samples. Current scored frames contain no detected sheep pixels.','tab:motion-history-audit',['Ages','Windows','Any prior evidence','Mean frames','Range'],history_rows))
    for source in ['L0','L4']:
        for layout in ['pooled','layout_01','layout_04']:
            rows=[]
            for model,label in LABELS.items():
                values=[]
                for ages in [[1,10],[11,15],[16,19],[1,19]]:
                    s='METADATA' if model.startswith(('META','ORACLE')) else source
                    r=next(r for r in stats['summaries'] if r['model']==model and r['source']==s and r['condition']==source and r['layout']==layout and r['ages']==ages)
                    values.append(f"{r['rmse']['mean']:.3f}")
                rows.append([label,*values])
            text.append(table(f"Native paired-motion RMSE in {'air' if source=='L0' else 'stone'}, {layout.replace('_',' ')}. Columns show age intervals; units are blocks.",f'tab:motion-{source}-{layout}',['Readout','1--10','11--15','16--19','1--19'],rows))
    text.append(r'\clearpage')
    rows=[]
    for model,label in LABELS.items():
        s='METADATA' if model.startswith(('META','ORACLE')) else 'L4'
        r=next(r for r in stats['summaries'] if r['model']==model and r['source']==s and r['condition']=='L4' and r['layout']=='pooled' and r['ages']==[1,10])
        e=r['rmse'];contrast=r['contrast_rmse'];agreement=r['sign_agreement']
        rows.append([label,f"{e['mean']:.3f}",f"[{e['ci'][0]:.3f}, {e['ci'][1]:.3f}]",f"{contrast['mean']:.3f}",f"{100*agreement['mean']:.1f}\\%" if agreement else '--'])
    text.append(table('Primary opaque paired-motion results with 95\\% family-bootstrap intervals. Contrast error measures prediction differences between variants against their target differences. Sign agreement is descriptive, not a qualification gate.','tab:motion-contrasts',['Readout','RMSE','Interval','Contrast RMSE','Sign'],rows))
    for model in ['MW_700M','PIXEL_HISTORY16','VIDEOMAE_S']:
        rows=[]
        for source in ['L0','L4']:
            rows.append(['Air' if source=='L0' else 'Stone',*[f"{next(r for r in stats['summaries'] if r['model']==model and r['source']==source and r['condition']==c and r['layout']=='pooled' and r['ages']==[1,10])['rmse']['mean']:.3f}" for c in ['L0','L4']]])
        text.append(table(f'{LABELS[model]} unchanged-decoder transfer on new held-out motion families, ages 1--10. Rows train and columns test.',f'tab:motion-transfer-{model}',['Source','Air','Stone'],rows))
    text.append(r'\clearpage')
    for model in ['OPACITY_MW','OPACITY_PIXELS']:
        rs=read(ROOT/'central'/f'{model}_statistics.json')['results'];levels=['A000','A025','A050','A075','A100'];rows=[]
        for source in levels:rows.append([str(int(source[1:])/100),*[f"{next(r['rmse'] for r in rs if r['source']==source and r['condition']==c):.3f}" for c in levels]])
        text.append(table(('MineWorld' if model=='OPACITY_MW' else 'History pixels')+' cross-opacity RMSE. Rows give training opacity and columns give test opacity. Fitted scales and coefficients stay unchanged across each row.',f'tab:opacity-{model}',['Source','0','0.25','0.5','0.75','1'],rows))
    rows=[]
    for c in ['L0','L1','L2','L3','L4']:
        rows.append([c,*[f"{next(r['rmse'] for r in read(ROOT/'central'/f'{m}_statistics.json')['results'] if r['source']==c and r['condition']==c):.3f}" for m in ['FRAME_DIFF16','FLOW16','VIDEOMAE_S']]])
    text.append(table('Complete stronger equal-history comparison on the central cohort. Mean identity RMSE, blocks.','tab:stronger-history',['Condition','Frame differences','Optical flow','VideoMAE-S'],rows))
    path=PAPER/'extension_results.tex';assert not path.exists();path.write_text('\n'.join(text))
    print('EXTENSION_TABLES_GENERATED',flush=True)

if __name__=='__main__':main()
