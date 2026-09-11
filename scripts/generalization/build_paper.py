"""Build a preserved new manuscript from verified fresh-cohort results."""
import json
from pathlib import Path
import shutil
from prepare import ROOT,SOURCE,read

PAPER=SOURCE/'generalization_outputs/paper'
OLD=SOURCE/'replication_outputs/paper'


def replace_once(text,old,new):
    assert text.count(old)==1,(old[:100],text.count(old))
    return text.replace(old,new)


def main():
    result=read(ROOT/'analysis/statistics.json')
    transfer=read(ROOT/'analysis/transfer_statistics.json')
    assert result['cells']==19950 and transfer['cells']==5700
    summary={(r['cohort'],r['condition'],r['model']):r for r in result['summaries']}
    contrasts={(r['cohort'],r['condition'],r['contrast']):r for r in result['paired_contrasts']}
    ts={(r['cohort'],r['condition'],r['model']):r for r in transfer['summaries']}
    cohorts=['replication','geometry','speed']
    labels={'replication':'Fresh original setting','geometry':'Changed geometry','speed':'Higher speed'}
    def value(c,condition='L4',model='MW_RGB_L19'):
        return summary[c,condition,model]['rmse']['mean']
    def span(values):
        return f'{min(values):.3f}--{max(values):.3f}'
    PAPER.mkdir(parents=True,exist_ok=True)
    # Copy only manuscript inputs, not old build logs or rendered review pages.
    assets=['neurips_2026.sty','references.bib','checklist.tex','matched_captures.pdf',
            'rgb_evidence_results.pdf','rgb_history_results.pdf']
    assets += [p.name for p in OLD.glob('rgb_*_rows.tex')]
    for name in assets:
        shutil.copy2(OLD/name,PAPER/name)
    text=(OLD/'paper.tex').read_text()
    abstract=r'''Evaluating object-state representations under occlusion requires separating visual evidence from motion predictability. We introduce MineOcclude, a paired protocol that replays identical Minecraft trajectories across no wall, three stained-glass materials, and an opaque wall. Renderer geometry defines common evaluation times, and aligned server state supplies continuous position targets. A fixed readout of frozen MineWorld is evaluated with verified RGB inputs and identity-grouped nested fitting. On the 25-identity graded-evidence cohort, mean trajectory RMSE is 0.083--0.107 blocks in visible and glass conditions and 1.600 under stone. A ridge baseline receiving the same 16-image history reaches 1.818 under stone; the paired neural advantage is 0.218 blocks (95\% identity-bootstrap interval [0.173, 0.265]). Native shorter windows yield higher opaque error. We additionally collect 75 fresh identities across an original-setting replication, changed geometry, and a 50\% higher speed. With separately refitted probes, opaque neural errors range from @MW@ blocks, versus @PIX@ for history pixels. Fixed-probe transfer is reported separately. These comparisons distinguish accessible position from trajectory predictability and characterize the evaluated reset-window readout, not a general limit on hidden-state representation.'''
    abstract=abstract.replace('@MW@',span([value(c) for c in cohorts])).replace('@PIX@',span([value(c,model='PIXEL_HISTORY16') for c in cohorts]))
    begin=text.index('\\begin{abstract}')+len('\\begin{abstract}')
    end=text.index('\\end{abstract}')
    text=text[:begin]+'\n'+abstract+'\n'+text[end:]
    text=replace_once(text,'We recover the original captures and predictions, then repeat extraction with verified RGB inputs and add a baseline receiving the same image history. This follow-up reuses the central identities; it is not a third independent cohort.',
        'Verified RGB extraction and a history-matched pixel comparator first refine this study on the same central identities. A subsequent extension collects 75 fresh identities to test an original-setting replication, changed geometry, and higher speed. The fresh extension uses the fixed readout family and remains separate from the five-material study.')
    text=replace_once(text,'Third, a diagnostic case study shows how visible decoding, opaque decoding, and trajectory predictability give different assessments of the same representation.',
        'Third, history-matched comparisons and native context-length tests separate available observations from readout performance, while fresh-cohort and fixed-probe transfer tests assess the reach of the observed pattern.')
    text=replace_once(text,'Last-seen holds the FIR-aligned position from the last counterfactual row that was not fully occluded.',
        'Last-seen holds the raw server position from the last counterfactual row that was not fully occluded.')
    text=replace_once(text,'Constant velocity fits position against time over the last ten pre-occlusion positions by ordinary least squares and extrapolates to the target tick.',
        'Constant velocity fits raw server position against time over the last ten pre-occlusion positions and extrapolates to the target tick. Both are scored against the aligned target; their privileged raw inputs match the executed implementation.')
    text=text.replace('Privileged aligned position at the last non-fully-occluded row','Privileged raw server position at the last non-fully-occluded row')
    text=text.replace('Ten privileged pre-occlusion aligned positions','Ten privileged pre-occlusion raw server positions')
    text=replace_once(text,'At load time, each vector is divided by its \\texttt{math.fsum}; filtered sums also use \\texttt{math.fsum}.',
        'At load time, each vector is divided by its \\texttt{math.fsum}; historical exact reconstruction also accumulates filtered values with \\texttt{math.fsum}. The fresh extension uses the existing FIR helper\'s binary64 summation; its independently checked difference is below $2\\times10^{-15}$ blocks.')
    methodology=r'''
\subsection{Fresh-cohort extension}
\label{sec:fresh-method}
We collect 75 additional identities, 25 per setting: the original geometry at 2.0 blocks/s, a farther sheep/wall arrangement at 2.0 blocks/s, and the original geometry at 3.0 blocks/s. Each has paired air/stone captures, 13 left-to-right and 12 right-to-left paths, and 19 geometry-selected target times. Seeds are distinct from prior data and engineering pilots. The fixed RGB layer-19 coarse readout, 16-pair context, alpha grid, and grouped procedure are retained. We report separate within-setting fits, not a newly selected representation. The secondary transfer test selects alpha using only the fresh original-setting cohort, fits all 25 source identities, and applies its unchanged scaler and probe to the other two settings. Appendix~\ref{app:fresh} specifies capture checks, geometry, target construction, and the distinction between refitting and transfer.

'''
    text=replace_once(text,'\\section{Experiments}',methodology+'\\section{Experiments}')
    # Keep the historical preprocessing comparison available in the appendix.
    a=text.index('\\subsection{Input convention and matched-runtime comparison}')
    b=text.index('\\subsection{Context age and decoder depth}',a)
    channel_section=text[a:b]
    text=text[:a]+text[b:]
    text=replace_once(text,'\\subsection{Additional central results and access}',channel_section+'\\subsection{Additional central results and access}')
    # The three ladder estimands remain stated in prose and in their full table.
    a=text.index('\\begin{table}[!htbp]\n  \\caption{RGB evidence-ladder estimates.')
    b=text.index('\\end{table}',a)+len('\\end{table}')
    primary_table=text[a:b]
    text=text[:a]+text[b:]
    text=replace_once(text,'\\subsection{Additional central results and access}',
        '\\subsection{Additional central results and access}\n'+primary_table)
    table=[]
    for c in cohorts:
        d=contrasts[c,'L4','MW_RGB_L19-minus-PIXEL_HISTORY16']
        table.append(f"{labels[c]} & {value(c,'L0'):.3f} & {value(c):.3f} & {value(c,model='PIXEL_HISTORY16'):.3f} & {d['mean']:.3f} & [{d['ci95'][0]:.3f}, {d['ci95'][1]:.3f}] \\\\")
    (PAPER/'fresh_rows.tex').write_text('\n'.join(table)+'\n')
    section=r'''
\subsection{Fresh identities, geometry, and speed}
\label{sec:fresh-results}
The extension adds 150 recordings and 2,850 target rows from 75 new identities. Table~\ref{tab:fresh} reports the fixed family's performance after within-setting refitting. All three cohorts are retained regardless of their ranking. Paired differences compare the neural and history-pixel readouts on exactly the same held-out identities and target times; they are not differences between independently resampled means.

\begin{table}[!htbp]
\caption{Fresh cohorts, 25 identities each. Mean identity RMSE in blocks after within-setting refitting. The last columns give neural minus history-pixel stone RMSE and its paired 95\% bootstrap interval; negative favors the neural readout.}
\label{tab:fresh}
\centering\small
\setlength{\tabcolsep}{4pt}
\begin{tabular}{@{}lrrrrl@{}}
\toprule
Setting & MW air & MW stone & History stone & Difference & 95\% CI\\
\midrule
\tablerows fresh_rows.tex
\bottomrule
\end{tabular}
\end{table}

Applying the unchanged fresh original-setting neural probe instead gives stone RMSE @G@ for changed geometry and @S@ for higher speed (Appendix~\ref{app:fresh}). These are transfer estimates, whereas Table~\ref{tab:fresh} allows a new scaler and probe in each setting. This distinction prevents condition-specific fitting from being interpreted as zero-shot generalization. Current-pixel and privileged-motion comparisons, all per-identity predictions, and age summaries are also retained.

'''.replace('@G@',f"{ts['geometry','L4','MW_RGB_L19']['rmse']['mean']:.3f}").replace('@S@',f"{ts['speed','L4','MW_RGB_L19']['rmse']['mean']:.3f}")
    text=replace_once(text,'\\subsection{Interpretation and limitations}',section+'\\subsection{Interpretation and limitations}')
    text=replace_once(text,'The central cohort is independent of readout development, but the follow-up reuses its 25 identities. It covers one layout, speed/noise regime, entity, and checkpoint. Corrected RGB and the same-runtime BGR comparison address input convention within this apparatus, not generalization to other physical conditions. A new cohort would be required for independent confirmation of the revised comparisons.',
        'The graded-evidence follow-up reuses its 25 central identities. The fresh extension adds independent trajectories, a second spatial arrangement, and a second speed, but still uses one entity, one checkpoint, and one noise regime. It tests air and stone only, not replication of the full glass ladder. The changed geometry jointly alters several spatial factors. Its software-rendered capture runtime also differs from the recovered historical runtime, so fresh-versus-historical differences cannot be attributed to trajectory sampling alone.')
    text=replace_once(text,'Glass appearance changes alongside measured evidence, and separately fitted probes do not test transfer between conditions.',
        'Glass appearance changes alongside measured evidence. The secondary transfer analysis changes geometry or speed, not material; it does not establish cross-material transfer.')
    a=text.index('\\section{Conclusion}')
    b=text.index('\\clearpage',a)
    conclusion=r'''\section{Conclusion}
MineOcclude provides a paired protocol for comparing visual evidence, linear position decoding, and motion predictability. On the graded-evidence cohort, verified RGB readouts achieve low error in air and glass, while history matching narrows the neural advantage under stone to 0.218 blocks. The 75-identity extension tests the fixed readout across fresh trajectories, geometry, and speed, with within-setting refitting and unchanged-probe transfer reported separately. Compact held-out predictions, targets, folds, and reconstruction code make these comparisons inspectable. The findings concern finite reset-window readouts, not a general claim about physical reasoning or all forms of hidden-state representation.

'''
    text=text[:a]+conclusion+text[b:]
    appendix=r'''
\section{Fresh-cohort capture and generalization details}
\label{app:fresh}
The extension's roster and primary analysis were fixed before neural or pixel decoding outcomes were inspected. It contains 75 new deterministic seeds, disjoint from seeds in historical repository records and from six engineering-pilot identities. Each setting has 13 left-to-right and 12 right-to-left paths. Starts are sampled uniformly at magnitudes 7.3--7.9 blocks on the corresponding side of the lane. The same drift-plus-noise generator uses $q=0.05$, $\Delta t=0.05$ s, and 180 frames. Candidates must provide 19 consecutive counterfactual fully occluded rows after at least 16 input frames, no lane-boundary clamp on target rows, and aligned target standard deviation above 0.10 blocks. These geometry/target-spread checks precede readout outcomes; the roster retains candidate rejections. No failed or unfavorable decoding result is replaced.

The original arrangement has sheep depth $z=6$ and wall depth $[2,3]$. The geometry extension moves the sheep to $z=8$ and wall to $[3,4]$, retaining the same wall-parallel lane and locked eye position $(0.5,5.6200000048,-5.5)$. Thus it changes apparent object scale and occluding geometry together. The speed extension retains the original arrangement but raises drift magnitude from 2.0 to 3.0 blocks/s. All conditions use air or stone; the central glass calibration values are not assigned to these new scenes.

\begin{figure}[!htbp]
\centering
\includegraphics[width=.82\linewidth]{fresh_captures.pdf}
\caption{Actual fresh-cohort recordings. Each row shows one identity's air/stone pair at its first selected target time. The same state and time are used within each pair; different rows are different identities and need not have equal position. These are captured Minecraft inputs, not model generations.}
\label{fig:fresh-captures}
\end{figure}

An isolated Minecraft 1.16.5/Fabric runtime runs under Xvfb with Mesa llvmpipe software rendering. The original capture mod is rebuilt without source edits. Twelve disjoint engineering captures cover both directions in all three settings and both materials. Mandatory present/absent/present liveness checks, physical receipts, drained writers, exact tick/frame/action joins, image dimensions, camera state, and target identity are verified. Production validation independently regenerates every path and target, checks exact air/stone pairing, and checks the magenta sheep is visible in air and absent in all opaque target images. This pixel check validates the selected geometry; it does not shift target times or replace labels.

The historical direction-specific FIR target definition is retained, not recalibrated on decoding outcomes. On visible pilot images, projected silhouette motion is checked against these labels with centered RMSE below 0.15 blocks and median offset magnitude below 0.30 blocks. Silhouette centers include view-dependent wool geometry, so this is an engineering motion-alignment diagnostic rather than an exact measurement of the rendered entity origin. The observed offsets are not used to modify labels. The admission receipt records this limitation and all pilot checks.

Within each setting, successive admitted identity indices are assigned to five outer folds modulo five. Each condition of an identity stays in the same fold. Four remaining groups provide inner rotations. All 150 captures contribute 19 rows, yielding 2,850 targets and 19,950 primary prediction cells across seven predictors. The source-only transfer analysis uses all 25 fresh original-setting identities after five-fold source-only alpha selection and evaluates 50 destination identities. Its 5,700 cells are kept separately. Destination labels are not used for scaling, fitting, or alpha selection.

Transfer removes exactly constant source-training columns before scaling, including inside each source-validation fold, and freezes that mask for destination prediction. This source-only safeguard was specified before outcomes to avoid spurious weights from round-off in repeated pixel values. The primary within-setting fits retain the historical-compatible implementation. Transfer is consequently a separately documented estimator, not an exact reuse of an outer-fold fit from the primary table.

Higher speed also changes the distance traveled within the fixed 19-age evaluation window and its target spread. The resulting setting-specific errors are not an isolated causal estimate of forgetting rate. Within each air/stone pair, positions and evaluation times remain exactly matched.

\begin{table}[!htbp]
\caption{Fresh-cohort comparator RMSE after within-setting fitting (blocks). Motion predictors use privileged state or metadata, not the same information as image-based methods.}
\centering\small
\begin{tabular}{@{}llrrrr@{}}
\toprule
Setting & Material & Current pixels & Direction/age & Last-seen & Constant velocity\\
\midrule
\tablerows fresh_baselines_rows.tex
\bottomrule
\end{tabular}
\end{table}

\begin{table}[!htbp]
\caption{Secondary unchanged-probe transfer RMSE (blocks). Scalers, alpha selection, and probe fitting use only the fresh original-setting cohort. These are not within-setting cross-validation estimates.}
\centering\small
\begin{tabular}{@{}llrrr@{}}
\toprule
Destination & Material & MineWorld & Current pixels & History pixels\\
\midrule
\tablerows fresh_transfer_rows.tex
\bottomrule
\end{tabular}
\end{table}

Raw server position, rather than the aligned target series, supplies last-seen and constant-velocity inputs. This wording follows the actual historical loader and the fresh implementation; an earlier baseline module docstring called these inputs aligned. The supervised/scored target remains the direction-specific FIR quantity in every condition. This documentation correction does not change historical numerical results.

The compact extension package contains all primary and transfer predictions, exact targets and folds, capture hashes, the frozen protocols, engineering receipts, and CPU-only rebuilding scripts. Hash verification and reconstruction of every reported summary are performed independently of feature extraction. Full refitting additionally needs the captured images and checkpoint; the compact package does not redistribute Minecraft binaries or model weights. Anonymous public distribution still requires a separate release and access check.

'''
    text=replace_once(text,'\\section{Readout-development provenance}',appendix+'\\section{Readout-development provenance}')
    lines=[]
    for c in cohorts:
        for condition in ['L0','L4']:
            numbers=[value(c,condition,m) for m in ['PIXEL_CURRENT','DIRECTION_AGE','ORACLE_LAST_SEEN','ORACLE_CONSTANT_VELOCITY']]
            lines.append(labels[c]+' & '+('Air' if condition=='L0' else 'Stone')+' & '+' & '.join(f'{v:.3f}' for v in numbers)+r' \\')
    (PAPER/'fresh_baselines_rows.tex').write_text('\n'.join(lines)+'\n')
    lines=[]
    for c in ['geometry','speed']:
        for condition in ['L0','L4']:
            numbers=[ts[c,condition,m]['rmse']['mean'] for m in ['MW_RGB_L19','PIXEL_CURRENT','PIXEL_HISTORY16']]
            lines.append(labels[c]+' & '+('Air' if condition=='L0' else 'Stone')+' & '+' & '.join(f'{v:.3f}' for v in numbers)+r' \\')
    (PAPER/'fresh_transfer_rows.tex').write_text('\n'.join(lines)+'\n')
    (PAPER/'paper.tex').write_text(text)
    checklist=(PAPER/'checklist.tex').read_text()
    checklist=checklist.replace('They distinguish the development cohort from the 25 reused central identities,',
        'They distinguish the development cohort, the 25 reused central identities, and the 75 newly captured extension identities,')
    checklist=checklist.replace('Sections 4.2--4.6 report the results and scope.','The experiments report central results, fresh-cohort refitting, and fixed-probe transfer separately.')
    checklist=checklist.replace('Section 4.6 discusses the single-apparatus cohort, reuse of central identities in the follow-up,','The interpretation subsection discusses the limited settings, reuse of central identities in the RGB follow-up,')
    checklist=checklist.replace('five matched example images.','matched example images and the fresh 75-identity extension.')
    checklist=checklist.replace('Sections 3.1--3.5 describe','Sections 3.1--3.6 describe')
    (PAPER/'checklist.tex').write_text(checklist)
    print('NEW_PAPER_SOURCE',PAPER)


if __name__=='__main__':
    main()
