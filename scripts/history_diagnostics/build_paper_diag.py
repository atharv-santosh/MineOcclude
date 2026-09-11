"""Generate a separate manuscript from validated observed results only."""
from diag_common import *
import shutil
import zipfile
import re

OUT=ROOT/'analysis'
PAPER=SOURCE/'history_diagnostic_outputs/paper'
OLD=SOURCE/'generalization_outputs/paper'


def replace_once(text,old,new):
    assert text.count(old)==1,(old[:80],text.count(old))
    return text.replace(old,new)


def block(text,start,end):
    a=text.index(start); b=text.index(end,a)+len(end)
    return text[:a]+text[b:],text[a:b]


def main():
    assert read(OUT/'independent_validation.json')['status']=='PASS'
    assert read(OUT/'comparator_replay_validation.json')['status']=='PASS'
    stats=read(OUT/'statistics.json')
    optimizer=read(OUT/'optimizer_check/statistics.json')
    def optimized(model,c='L4'):
        return next(r['rmse']['mean'] for r in optimizer['summaries'] if r['model']==model+'_MLP_OPT10K' and r['condition']==c and r['phase']=='correct' and r['layout']=='pooled' and r['ages']=='1-10')
    lookup={(r['model'],r['setting'],r['condition'],r['phase'],r['layout'],r['ages']):r for r in stats['summaries']}
    def metric(m='MW_700M',c='L4',phase='correct',layout='pooled',ages='1-10',setting='native'):
        return lookup[m,setting,c,phase,layout,ages]['rmse']['mean']
    def intervention(m,phase):
        return next(r['rmse_difference'] for r in stats['interventions'] if r['model']==m and r['phase']==phase and r['layout']=='pooled' and r['ages']=='1-10')
    def interval(v):
        return f"$[{v['ci95'][0]:.3f},{v['ci95'][1]:.3f}]$"
    swap=intervention('MW_700M','swapped'); removal=intervention('MW_700M','removed')
    pixel_difference=next(r['rmse_difference'] for r in stats['paired_contrasts'] if r['first']=='MW_700M' and r['second']=='PIXEL_HISTORY16' and r['condition']=='L4' and r['layout']=='pooled' and r['ages']=='1-10')
    response=next(r for r in stats['history_responses'] if r['model']=='MW_700M' and r['layout']=='pooled' and r['ages']=='1-10')
    tracker=next(r for r in stats['tracker_coverage'] if r['condition']=='L4' and r['phase']=='correct' and r['ages']=='1-10')
    shifted='increases' if swap['mean']>=0 else 'decreases'
    PAPER.mkdir(parents=True,exist_ok=True)
    for p in OLD.iterdir():
        if p.suffix in ('.tex','.bib','.sty','.pdf') and p.name not in ('paper.tex','paper.pdf'):
            shutil.copy2(p,PAPER/p.name)
    kit=SOURCE/'history_diagnostic_outputs/official_neurips_2026_author_kit.zip'
    assert sha(kit)=='82473931e3ef710fcd3f4a8cd4119b9de32e56825f90f9e5a6d55f2d01b817d9'
    with zipfile.ZipFile(kit) as z:
        (PAPER/'neurips_2026.sty').write_bytes(z.read('neurips_2026.sty'))
        official_questions=re.findall(r'Question: (.*)',z.read('checklist.tex').decode())
    save(PAPER.parent/'official_style_receipt.json',dict(status='PASS',source='https://media.neurips.cc/Conferences/NeurIPS2026/Formatting_Instructions_For_NeurIPS_2026.zip',author_kit_sha256=sha(kit),style_sha256=sha(PAPER/'neurips_2026.sty'),style_modified=False,official_checklist_questions=16))
    shutil.copy2(Path(__file__).parent/'diagnostic_appendix.tex',PAPER/'diagnostic_appendix.tex')
    text=(OLD/'paper.tex').read_text()
    text=replace_once(text,r'\title{MineOcclude: A Paired Visual-Evidence Benchmark for Object-Position Decoding}',r'\title{MineOcclude: Separating Visual Evidence, History, and Motion Predictability}')
    abstract=f'''Evaluating object-state representations under occlusion requires separating visual evidence, available history, and motion predictability. MineOcclude replays identical Minecraft trajectories across air, stained glass, and stone, with shared evaluation times and aligned continuous position targets. On a 25-identity graded-evidence cohort, a fixed frozen-MineWorld readout with verified RGB inputs reaches 0.083--0.107 blocks RMSE in air and glass and 1.600 under stone; a ridge baseline with the same 16-image history reaches 1.818. A variable-speed diagnostic adds 48 separate training and 48 held-out identities across two layouts and two MineWorld model sizes. At occlusion ages 1--10, 700M ridge RMSE is {metric():.3f} blocks, compared with {metric('PIXEL_HISTORY16'):.3f} for history pixels and {optimized('MW_700M'):.3f} for a converged nonlinear probe. Removing prior images increases ridge RMSE by {removal['mean']:.3f} blocks, but swapped-history responses do not reliably follow donor position. Direction and age remain strongly predictive at {metric('DIRECTION_AGE'):.3f} blocks, and visible-only geometry calibration improves visible transfer without recovering hidden decoding. The protocol distinguishes input-history sensitivity, readout accuracy, and task predictability in finite-window world-model representations.'''
    a=text.index(r'\begin{abstract}')+len(r'\begin{abstract}'); b=text.index(r'\end{abstract}')
    text=text[:a]+'\n'+abstract+'\n'+text[b:]
    text=replace_once(text,'A subsequent extension collects 75 fresh identities to test an original-setting replication, changed geometry, and higher speed. The fresh extension uses the fixed readout family and remains separate from the five-material study.',
        'A 75-identity extension tests fresh trajectories, changed geometry, and higher speed. Motivated by those comparisons, a prospectively fixed variable-speed diagnostic adds 48 training and 48 untouched test identities across two layouts, with history substitutions and a second MineWorld model size.')
    text=replace_once(text,'Third, history-matched comparisons and native context-length tests separate available observations from readout performance, while fresh-cohort and fixed-probe transfer tests assess the reach of the observed pattern.',
        'Third, history-matched baselines, native context-length comparisons, and prospective history substitutions distinguish input-history dependence from motion predictability; nonlinear probes and visible-only calibration examine estimator and geometry dependence.')
    # Keep full input accounting in the appendix without spending a main-text table.
    text,baseline_table=block(text,r'\begin{table}[!htbp]\n\caption{Predictors receive different information.'.replace('\\n','\n'),r'\end{table}')
    text,age_table=block(text,r'\begin{table}[!htbp]\n  \caption{Corrected RGB: descriptive mean identity RMSE'.replace('\\n','\n'),r'\end{table}')
    text,history_figure=block(text,r'\begin{figure}[t]\n\centering\n\includegraphics[width=\linewidth]{rgb_history_results.pdf}'.replace('\\n','\n'),r'\end{figure}')
    text,fresh_table=block(text,r'\begin{table}[!htbp]\n\caption{Fresh cohorts, 25 identities each.'.replace('\\n','\n'),r'\end{table}')
    text=text.replace('\\newpage\n\\subsection{Fresh identities, geometry, and speed}','\\subsection{Fresh identities, geometry, and speed}')
    a=text.index(r'\subsection{Fresh-cohort extension}'); b=text.index(r'\section{Experiments}',a)
    methodology=r'''\subsection{Prospective history and transfer tests}
\label{sec:fresh-method}
An initial extension collects 75 fresh identities across the original setting, changed geometry, and higher speed, with separate within-setting fits and unchanged-probe transfer (\autoref{app:fresh}). We then freeze a variable-speed diagnostic with 24 training and 24 test identities in each of two layouts, balanced by direction. Within each direction and split, six speeds are sampled from $[0.8,1.6]$ and six from $[2.4,3.2]$ blocks/s. All 96 identities are new and have paired air/stone captures. Four folds within the training set select ridge alpha; test identities are untouched by selection.

The primary interval is ages 1--10. Correct histories are compared with reciprocal slow/fast donor histories at the same age and with histories replaced by the repeated current image. Every intervention keeps that current image and the no-op actions fixed. Probes are trained only on correct histories. We retain the 700M final-layer coarse readout and evaluate the corresponding 300M model, plus a small nonlinear probe using training-only 64-dimensional PCA and 32 tanh hidden units. An image-only tracker estimates velocity from reliable sheep detections inside the same 16-image window. These are fixed secondary comparisons, not a new layer search.

For geometry transfer, a source probe is tested unchanged or with a shared affine output calibration fitted only on six predesignated destination-training air identities. Hidden destination labels are not used for calibration. Native destination fits provide a separate reference. New diagnostic intervals use 10,000 bootstrap draws, seed 930119, resampling identities for predictor comparisons and reciprocal donor pairs for intervention differences. Full architecture, optimizer, detector, split, and calibration specifications appear in \autoref{app:diagnostic}.

'''
    text=text[:a]+methodology+text[b:]
    a=text.index(r'\subsection{Fresh identities, geometry, and speed}'); b=text.index(r'\subsection{Interpretation and limitations}',a)
    diagnostic=f'''\\subsection{{Fresh identities and history dependence}}
\\label{{sec:fresh-results}}
The initial 75-identity extension repeats the neural advantage over history pixels in the original setting and at higher speed, but not conclusively under changed geometry. Unchanged geometry transfer also degrades visible decoding, so this sensitivity is not specific to occlusion (\\autoref{{tab:fresh}}; \\autoref{{app:fresh}}). This motivates the separate variable-speed test, where timing and direction no longer imply a single nominal speed.

On its 48 held-out identities, correct-history stone RMSE at ages 1--10 is {metric():.3f} blocks for 700M ridge, {metric('MW_300M'):.3f} for 300M ridge, and {metric('PIXEL_HISTORY16'):.3f} for history pixels (\\autoref{{fig:diagnostic}}). The pooled 700M-minus-pixel difference is {pixel_difference['mean']:.3f}, interval {interval(pixel_difference)}, so this comparison alone does not establish an advantage. Direction-and-age reaches {metric('DIRECTION_AGE'):.3f} without commanded speed: varying speed does not eliminate trajectory predictability. Image tracking reaches {metric('IMAGE_TRACKER_CV'):.3f}, but falls back to the training mean on {100*tracker['fallback_fraction']:.1f}\\% of these rows, limiting that comparator.

The nonlinear probes reach {metric('MW_700M_MLP'):.3f} and {metric('MW_300M_MLP'):.3f} under the original iteration cap. Training-limit warnings trigger a separate, fixed-configuration optimization check; all extended fits converge, reaching {optimized('MW_700M'):.3f} and {optimized('MW_300M'):.3f}. Both budgets remain reported in \\autoref{{app:diagnostic}}. This improves on ridge but does not remove the gap to motion metadata.

Replacing history with the current image raises 700M RMSE by {removal['mean']:.3f} blocks, interval {interval(removal)}. Swapping matched-direction histories instead changes it by {swap['mean']:.3f}, donor-pair interval {interval(swap)}. Although the absolute prediction shift averages {response['absolute_prediction_shift']['mean']:.3f} blocks, its sign agrees with donor-minus-recipient position on only {100*response['donor_direction_agreement']['mean']:.1f}\\% of rows. Thus input-history sensitivity is not evidence of reliable donor-position tracking. Ages 16--19 and all model responses are retained separately in \\autoref{{app:diagnostic}}.

\\begin{{figure}}[t]
\\centering
\\includegraphics[width=\\linewidth]{{history_diagnostic_results.pdf}}
\\caption{{Variable-speed diagnostic, 48 held-out identities at ages 1--10. (a) Correct-history performance; the nonlinear bar uses the converged optimization-check fit, while direction and age are privileged metadata. (b) History substitutions keep the current image fixed. Error bars are 95\\% identity-bootstrap intervals. Paired intervention differences use reciprocal-donor-pair intervals, reported in the text.}}
\\label{{fig:diagnostic}}
\\end{{figure}}

For the 700M probe on changed geometry, frozen-transfer air/stone errors are {metric(c='L0',layout='layout_04',setting='frozen_transfer'):.3f}/{metric(layout='layout_04',setting='frozen_transfer'):.3f} blocks. Visible-only output calibration gives {metric(c='L0',layout='layout_04',setting='visible_calibrated_transfer'):.3f}/{metric(layout='layout_04',setting='visible_calibrated_transfer'):.3f}, compared with {metric(c='L0',layout='layout_04'):.3f}/{metric(layout='layout_04'):.3f} after native fitting. Calibration recovers much of the visible accuracy but not hidden decoding, so a shared affine output correction is insufficient for this transfer.

'''
    text=text[:a]+diagnostic+text[b:]
    a=text.index(r'\subsection{Interpretation and limitations}'); b=text.index(r'\clearpage\n\bibliographystyle'.replace('\\n','\n'),a)
    ending=r'''\subsection{Interpretation and limitations}
\label{sec:limitations}
The material ladder separates current visual evidence from predictability; the new held-out diagnostic additionally tests sensitivity to prior images, estimator class, model size, and spatial transfer. These results concern observable position accessibility in finite reset windows, not downstream planning, calibrated uncertainty, or continuous state maintenance.

The original RGB follow-up reuses 25 central identities. Subsequent capture adds 75 exploratory extension identities and a separate prospective split of 48 training and 48 test identities. Breadth remains limited to one entity, one stochastic motion family, two layouts, and two sizes of the same pretrained model family. Fresh captures use software rendering, so historical-to-fresh differences are not attributable solely to trajectory sampling. Glass appearance changes with evidence, and geometry changes several spatial factors together.

Matching image history does not match resolution, pretraining, or total estimator capacity. The nonlinear probe is small, and the tracker uses a known-color detector with an explicit fallback when reliable observations are absent. Swapping and removing history change the input distribution and cannot alone establish an internal memory mechanism. Bootstrap intervals exclude refitting uncertainty and multiple-comparison adjustment. The prediction package makes these separate comparisons inspectable without pooling cohorts or selecting only favorable outcomes.

\section{Conclusion}
MineOcclude provides a paired protocol for separating visual evidence, history-dependent position decoding, and motion predictability. The graded-material study shows accurate RGB decoding through glass and a more demanding opaque condition. New held-out variable-speed trajectories extend the evaluation to two model sizes, nonlinear readouts, input-history substitutions, image tracking, and visible-only geometry calibration. The resulting comparisons identify estimator and input dependencies while keeping model-derived, image-based, and privileged motion predictions distinct. This supports controlled evaluation of object-position information in finite-window world-model representations.

'''
    text=text[:a]+ending+text[b:]
    text=replace_once(text,r'\subsection{Additional central results and access}',baseline_table+'\n'+age_table+'\n'+history_figure+'\n'+r'\subsection{Additional central results and access}')
    text=replace_once(text,r'\section{Fresh-cohort capture and generalization details}',fresh_table+'\n'+r'\section{Fresh-cohort capture and generalization details}')
    text=replace_once(text,'Such a new checkpoint evaluation is an intended use of the protocol, not an experiment reported here.',
        'The prospective diagnostic in \\autoref{app:diagnostic} implements this comparison for a second MineWorld model size while keeping its family and input convention fixed.')
    extra=r'''
\clearpage
\input{diagnostic_appendix}
\begin{figure}[!htbp]
\centering
\includegraphics[width=\linewidth]{history_intervention_inputs.pdf}
\caption{Actual image-history substitutions for the first predetermined original-layout, left-to-right slow test identity at age 1. Four of the 16 input times are displayed. The swapped row uses its preassigned fast donor for earlier images and the recipient for the current image. The removed row repeats the recipient current image. Images are recorded inputs, not generated illustrations or outcomes selected for visual effect.}
\label{fig:history-inputs}
\end{figure}
\input{diagnostic_tables}
\input{diagnostic_compute}

'''
    text=replace_once(text,'\\clearpage\n\\input{checklist}',extra+'\\clearpage\n\\input{checklist}')
    (PAPER/'paper.tex').write_text(text)
    checklist=(PAPER/'checklist.tex').read_text()
    current_questions=re.findall(r'Question: (.*)',checklist)
    assert len(current_questions)==len(official_questions)==16
    for old,new in zip(current_questions,official_questions):
        checklist=checklist.replace('Question: '+old,'Question: '+new)
    checklist=checklist.replace('and the 75 newly captured extension identities,','the 75 newly captured extension identities, and the prospective 48-training/48-test split,')
    checklist=checklist.replace('and the fresh 75-identity extension.','the fresh 75-identity extension, and the prospective variable-speed diagnostic.')
    checklist=checklist.replace('linear decodability from causal memory or absent model state.','linear and small nonlinear readouts from causal memory or absent model state.')
    declaration=checklist.index(r'\item {\bf Declaration of LLM usage}')
    checklist=checklist[:declaration]+checklist[declaration:].replace(r'\answerNA{}',r'\answerYes{}',1).replace('No LLM served as an experimental predictor or generated the capture images, labels, or reported measurements. Assistance was used for implementation, debugging, and manuscript preparation. Numerical claims are bound to executed model predictions and explicit validation checks; no hypothetical results are included.',
        'LLM assistance supported the prospective diagnostic design, implementation, analysis scripts, debugging, and manuscript preparation, as disclosed in the diagnostic appendix. It did not generate the capture images, targets, or reported numerical findings. Measurements are bound to executed captures and model predictions with explicit validation checks.')
    (PAPER/'checklist.tex').write_text(checklist)
    timings={p.stem:read(p) for p in (OUT/'job_logs').glob('*.json')}
    capture=read(ROOT/'capture_status.json')
    extract={m:read(OUT/f'{m}_complete.json') for m in ['700M','300M','pixels']}
    compute=f'''\\subsection{{Execution and reproducibility}}
The new diagnostic uses the same RTX 5090, Ryzen 9 9950X3D, and 64 GB workstation. Production capture takes {capture['elapsed_seconds']/60:.2f} minutes. Streaming 700M, 300M, and pixel-feature jobs finish in {extract['700M']['seconds']/60:.2f}, {extract['300M']['seconds']/60:.2f}, and {extract['pixels']['seconds']/60:.2f} minutes including time waiting for captures, so these are overlapping wall times rather than isolated inference costs. CPU fitting takes {timings['fit_700M']['elapsed_seconds']:.1f}, {timings['fit_300M']['elapsed_seconds']:.1f}, and {timings['fit_pixels']['elapsed_seconds']:.1f} seconds for the respective jobs, also overlapping. All 40,128 prediction cells pass target/split joins, saved-fit replay, and independent arithmetic checks. The compact snapshot includes predictions, targets, splits, fitted selections, protocols, provenance, and a CPU-only statistics rebuild. Full recorded captures are archived separately without Minecraft binaries or model weights. Public access is reported separately from local reconstruction success.

The separate optimization-budget check adds 7,296 prediction cells, with saved-fit replay and an independently runnable statistics rebuild. These are kept separate from the 40,128 original cells. The recorded-visibility validation repair changes an incorrect counting assertion only; the original predictions and statistics remain unchanged.

LLM assistance supported the prospective diagnostic design, implementation, analysis scripting, debugging, and manuscript revision. The reported measurements come from executed Minecraft captures and frozen MineWorld forwards, not generated numerical findings. Automated source, split, prediction, and arithmetic checks are supplied with the artifacts; they are not a claim of independent human replication.
'''
    (PAPER/'diagnostic_compute.tex').write_text(compute)
    print('NEW_MANUSCRIPT_WRITTEN',flush=True)


if __name__=='__main__':
    main()
