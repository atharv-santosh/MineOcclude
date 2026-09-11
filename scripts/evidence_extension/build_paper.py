from common import *
import shutil
import re

PAPER=SOURCE/'evidence_extension_outputs/paper'
PREVIOUS=SOURCE/'history_diagnostic_outputs/paper'

def replace_section(text,start,end,new):
    a=text.index(start);b=text.index(end,a)
    return text[:a]+new+'\n\n'+text[b:]

def main():
    assert read(ROOT/'PRODUCTION_COMPLETE.json')['status']=='PASS'
    assert read(ROOT/'motion/validation.json')['status']=='PASS'
    assert not (PAPER/'paper.tex').exists()
    PAPER.mkdir(parents=True,exist_ok=True)
    for p in PREVIOUS.iterdir():
        if p.suffix in ('.tex','.bib','.sty','.pdf','.png') and p.name not in ('paper.tex','paper.pdf'):
            if not (PAPER/p.name).exists():shutil.copy2(p,PAPER/p.name)
    stats=read(ROOT/'motion/statistics.json')
    def m(model='MW_700M',condition='L4',lo=1,hi=10,layout='pooled',source=None):
        s=source or ('METADATA' if model.startswith(('META','ORACLE')) else condition)
        return next(r for r in stats['summaries'] if r['model']==model and r['source']==s and r['condition']==condition and r['layout']==layout and r['ages']==[lo,hi])['rmse']['mean']
    def diff(b):return next(r for r in stats['paired_differences'] if r['baseline']==b and r['condition']=='L4' and r['layout']=='pooled' and r['ages']==[1,10])
    def ci(r):return f"$[{r['ci'][0]:.3f},{r['ci'][1]:.3f}]$"
    text=(PREVIOUS/'paper.tex').read_text()
    begin=text.index(r'\begin{abstract}')+len(r'\begin{abstract}');end=text.index(r'\end{abstract}')
    abstract=f'''Evaluating object-state representations under occlusion requires separating visual evidence, available history, and motion predictability. MineOcclude replays identical Minecraft trajectories across visual conditions with shared evaluation times and aligned continuous position targets. On 25 central identities, a fixed frozen-MineWorld readout with verified RGB inputs reaches 0.083--0.107 blocks RMSE in air and glass and 1.600 under stone. Its stone error is lower than those of matched-history pixels, optical flow, frame differences, and a pretrained VideoMAE-S readout, but unchanged decoders transfer poorly across materials. A fixed-texture opacity intervention separates appearance changes from the material comparison. A prospective extension adds 64 training and 64 held-out paired-motion families across two layouts, including acceleration, stops, and reversals. At ages 1--10, opaque RMSE is {m():.3f} blocks for MineWorld, {m('PIXEL_HISTORY16'):.3f} for history pixels, and {m('META_CUBIC'):.3f} for direction-and-age prediction. These controlled comparisons characterize finite-window position accessibility, not an identified mechanism of persistent object memory.'''
    text=text[:begin]+'\n'+abstract+'\n'+text[end:]
    old='A 75-identity extension tests fresh trajectories, changed geometry, and higher speed. Motivated by those comparisons, a prospectively fixed variable-speed diagnostic adds 48 training and 48 untouched test identities across two layouts, with history substitutions and a second MineWorld model size.'
    assert old in text
    text=text.replace(old,'Further studies test fresh trajectories, changed geometry, input-history substitutions, and a second MineWorld model size. The present extension adds unchanged cross-material transfer, stronger equal-history comparators, a fixed-appearance opacity sweep, and a prospective split of 64 training and 64 held-out paired-motion families with within-trajectory changes.')
    old='Third, history-matched baselines, native context-length comparisons, and prospective history substitutions distinguish input-history dependence from motion predictability; nonlinear probes and visible-only calibration examine estimator and geometry dependence.'
    text=text.replace(old,'Third, matched-history comparisons, native context-length tests, and new paired motions distinguish input-history dependence from trajectory predictability; unchanged-decoder transfer and a fixed-texture opacity intervention test whether the same readout survives changes in available evidence.')
    text=text.replace('then evaluates continuous position with condition-specific readouts in finite reset windows.','then evaluates continuous position with native and transferred readouts in finite reset windows. A frozen VideoMAE comparator adds pretrained video features to the equal-history comparison \\citep{tong2022videomae}.')
    text=text.replace('A separate probe is fitted per condition, measuring within-condition accessibility rather than transfer between materials.','A separate probe measures within-condition accessibility. We additionally fit a complete source-to-destination transfer matrix: every source-fold decoder, including its scaling and selected regularization, is tested unchanged on held-out identities in all five materials. Destination data are never used for tuning or calibration.')
    old='Neither receives age, direction, or oracle state. History is matched, but resolution and capacity are not: MineWorld supplies pretrained nonlinear features from higher-resolution images.'
    text=text.replace(old,'Neither receives age, direction, or oracle state. We add current-image plus ordered frame differences, current-image plus 15 dense Farneb\\"ack flow fields \\citep{farneback2003two}, and frozen VideoMAE-S features \\citep{tong2022videomae}. VideoMAE receives the same 16 RGB images, uses no classification head or fine-tuning, and supplies temporally averaged, coarse spatial features to ridge. Exact dimensions and preprocessing appear in \\autoref{app:extension}. These comparisons match history, not all resolutions or estimator capacities.')
    text=replace_section(text,r'\subsection{Prospective history and transfer tests}',r'\section{Experiments}',r'''\subsection{Controlled opacity and paired motions}
\label{sec:fresh-method}
To separate color and texture from opacity, a fixed stone texture is alpha-blended over the same geometry-defined wall mask in every image of the central air histories. We use $\alpha\in\{0,0.25,0.5,0.75,1\}$, leaving pixels outside the mask unchanged. Shared targets, actions, and folds permit native per-opacity fits and unchanged cross-opacity transfer. This is a synthetic evidence intervention, not a physical glass simulator.

The new motion cohort has 128 independent families, split equally into training and test. Each family contains two variants, captured in both air and stone. Within each split, two layouts and four motion types are balanced: velocity, acceleration, stop/resume, and reversal. Starts are adjusted to match the world position at the first full-occlusion target within direction and layout. The 512 captures use recorded deterministic schedules with visible pre-occlusion motion; they do not ask the model to identify an unobserved random event. Engineering pilots check actual image history, full occlusion, synchronization, and target alignment before production admission.

Four training-only family folds select ridge regularization separately within each layout; both variants remain together. All test families are held out from selection. Primary errors cover ages 1--10, with ages 11--15 and 16--19 reported separately. We average within variant and then within family; 10,000 family-bootstrap draws, stratified by layout and motion type, give descriptive intervals. Paired prediction contrasts test whether decoders distinguish different motions from the same entry position. Linear and cubic direction/age baselines assess residual predictability; a separate privileged baseline adds motion-type indicators. Exact schedules, seeds, pilot revisions, and analysis specifications are in \autoref{app:extension}.

Earlier fresh-cohort, model-size, nonlinear-probe, history-substitution, and geometry-calibration studies remain separately reported in \autoref{app:fresh} and \autoref{app:diagnostic}. Their observations motivate these additions but are not pooled with the new held-out families.''')
    text=replace_section(text,r'\subsection{From readout development to a new cohort}',r'\subsection{Position decoding across visual evidence}',r'''\subsection{From readout development to a new cohort}
The separate development cohort selects layer-19 coarse pooling; visible controls establish usable position decoding. The central study then evaluates the fixed family on 25 different identities across five materials. All five conditions are rerun with verified RGB inputs, with historical and same-runtime BGR results preserved in \autoref{app:central}. Transfer, opacity, and stronger comparators refine this central study on the same identities. The paired-motion cohort supplies a separate prospective test.''')
    # Preserve the original central result figure in the appendix, avoiding a duplicate main-text display.
    a=text.index('\\begin{figure}[t]\n\\centering\n\\includegraphics[width=\\linewidth]{rgb_evidence_results.pdf}')
    b=text.index(r'\end{figure}',a)+len(r'\end{figure}')
    oldfigure=text[a:b];text=text[:a]+text[b:]
    text=text.replace(r'\autoref{fig:graded-results} shows the corrected-RGB results.',r'\autoref{tab:exp3-condition} summarizes the corrected-RGB results.')
    text=text.replace(r'\subsection{Additional central results and access}',oldfigure+'\n'+r'\subsection{Additional central results and access}')
    pos=text.index(r'\subsection{Context age and decoder depth}')
    extra=r'''\subsection{Transfer and appearance-controlled opacity}
\label{sec:transfer-opacity}
The full transfer matrix separates a decodable position signal from a shared decoder (\autoref{fig:transfer-opacity}a). An air-trained probe gives 2.424, 2.384, 2.609, and 3.203 blocks on white glass, blue glass, brown glass, and stone, respectively. All off-diagonal cells are worse than the corresponding destination-native fit. Thus the accurate visible fits do not establish a condition-invariant linear mapping. Transfer sensitivity may reflect changed feature distributions rather than loss of every position representation.

With one fixed overlay texture, native MineWorld RMSE is 0.085, 0.088, 0.093, 0.095, and 1.742 as opacity increases from zero to one (\autoref{fig:transfer-opacity}b). History-pixel RMSE at full opacity is 3.304. An unchanged air-trained MineWorld decoder instead degrades to 1.704 at 25\% opacity and 3.226 at full opacity. The native and transferred curves answer different questions: position remains accessible after refitting at partial opacity, but the air decoder is not stable under this appearance change. Pixel-level checks verify exact zero-opacity identity and complete masking of scored sheep pixels at full opacity.

\begin{figure}[t]
\centering
\includegraphics[width=\linewidth]{transfer_opacity.pdf}
\caption{Central-cohort extensions. (a) Mean identity RMSE for frozen source-condition decoders; rows train and columns test. Color is logarithmic. (b) A fixed texture and mask with varying alpha. Native probes are refitted within training folds at each opacity; the dashed curve keeps the air decoder unchanged. Error bars are 95\% identity-bootstrap intervals conditional on fitted probes.}
\label{fig:transfer-opacity}
\end{figure}

'''
    text=text[:pos]+extra+text[pos:]
    pos=text.index(r'\subsection{Transfer and appearance-controlled opacity}')
    stronger=r'''Stronger equal-history comparators reach stone RMSEs of 1.781 for frame differences, 1.757 for optical flow, and 1.767 for VideoMAE-S. The paired MineWorld-minus-comparator differences are $-0.181$ ($[-0.229,-0.136]$), $-0.157$ ($[-0.187,-0.126]$), and $-0.167$ ($[-0.199,-0.134]$), respectively. These central-cohort intervals support a modest advantage over these specified alternatives, not a general memory claim. VideoMAE-S instead reaches 0.068--0.082 in air and glass, so MineWorld is not uniformly the strongest representation.

'''
    text=text[:pos]+stronger+text[pos:]
    a=text.index(r'\subsection{Fresh identities and history dependence}');b=text.index(r'\subsection{Interpretation and limitations}',a)
    olddiagnostic=text[a:b]
    result=f'''\\subsection{{Held-out paired motions}}
\\label{{sec:fresh-results}}
On the 64 held-out families, opaque error at ages 1--10 is {m():.3f} blocks for MineWorld, {m('PIXEL_HISTORY16'):.3f} for history pixels, and {m('VIDEOMAE_S'):.3f} for VideoMAE-S (\\autoref{{fig:matched-motion}}). The paired MineWorld-minus-history-pixel difference is {diff('PIXEL_HISTORY16')['mean']:.3f}, interval {ci(diff('PIXEL_HISTORY16'))}; the corresponding difference against VideoMAE-S is {diff('VIDEOMAE_S')['mean']:.3f}, interval {ci(diff('VIDEOMAE_S'))}. These family-based intervals retain both motion variants together.

Linear direction/age gives {m('META_LINEAR'):.3f} blocks, cubic direction/age {m('META_CUBIC'):.3f}, and the additional privileged motion-type information {m('META_FAMILY'):.3f}. Oracle constant velocity gives {m('ORACLE_CV'):.3f}. The comparison therefore reports remaining schedule predictability alongside neural accuracy instead of treating varied speed, stops, or reversals as sufficient evidence of memory.

MineWorld's air error is {m(condition='L0'):.3f}. A decoder fitted only in air gives {m(condition='L4',source='L0'):.3f} under stone, compared with {m():.3f} after native stone fitting. Opaque native errors in the two layouts are {m(layout='layout_01'):.3f} and {m(layout='layout_04'):.3f}. Across later intervals, pooled MineWorld RMSE is {m(lo=11,hi=15):.3f} at ages 11--15 and {m(lo=16,hi=19):.3f} at ages 16--19. Full type-specific, paired-contrast, and transfer results are retained in \\autoref{{app:extension-results}}.

\\begin{{figure}}[t]
\\centering
\\includegraphics[width=\\linewidth]{{matched_motion_results.pdf}}
\\caption{{Prospective paired-motion study, 64 held-out families across two layouts. (a) Opaque-condition errors at ages 1--10. Direction/age and motion type are metadata; oracle velocity uses privileged pre-occlusion state. (b) Errors across the available-history boundary. Intervals resample independent families, preserving paired variants and stratifying by layout and motion type.}}
\\label{{fig:matched-motion}}
\\end{{figure}}

'''
    text=text[:a]+result+text[b:]
    text=replace_section(text,r'\subsection{Interpretation and limitations}',r'\clearpage\n\bibliographystyle'.replace('\\n','\n'),r'''\subsection{Interpretation and limitations}
\label{sec:limitations}
The central study supports accurate visible decoding and a modest opaque-condition advantage over several equal-history representations. Cross-condition transfer and opacity show that within-condition accessibility does not imply a shared linear decoder. The independent paired-motion split further tests this distinction under controlled changes in dynamics and entry position. These measurements concern finite reset windows, not continuously maintained state or downstream planning.

Breadth now includes two layouts, several motion schedules, earlier higher-speed cohorts, and two sizes of the same MineWorld family, but still one entity and no independent world-model family beyond the VideoMAE comparator. New captures use software rendering, so comparisons with historical cohorts cannot isolate sampling alone. The opacity overlay controls texture and mask but is synthetic; the glass-material ladder remains visually confounded. Deterministic schedules can remain predictable from metadata. Matching history does not match all input resolutions, pretraining, or estimator capacities. Intervals condition on fitted probes and are not adjusted for all reported comparisons.

Identical input histories cannot identify an unobserved randomly chosen future. A constructed duplicate-input control verifies this information boundary and is not counted as successful hidden-state tracking. Evidence for object memory would require reliable use of informative history, beyond the particular prediction and transfer comparisons reported here. The compact snapshot makes these distinctions reproducible from predictions; anonymous access to the updated snapshot remains a separate submission check.

\section{Conclusion}
MineOcclude separates visual evidence, position accessibility, and trajectory predictability through paired captures and grouped evaluation. Verified RGB results are complemented by a full decoder-transfer matrix, stronger matched-history comparators, and a fixed-appearance opacity manipulation. A new held-out paired-motion cohort adds acceleration, stops, and reversals across two layouts. Together, these tests provide a controlled characterization of finite-window readouts while distinguishing native decoding from transfer and motion predictability.''')
    # Keep earlier prospective results intact as a separately labeled appendix.
    pos=text.index(r'\clearpage\n\input{checklist}'.replace('\\n','\n'))
    appendix='\n\\clearpage\n\\section{Earlier variable-speed diagnostic summary}\n'+olddiagnostic.replace(r'\subsection{Fresh identities and history dependence}',r'\subsection{Preserved results}').replace(r'\label{sec:fresh-results}',r'\label{app:earlier-summary}')+'\n\\clearpage\n\\input{extension_methods}\n\\input{extension_results}\n'
    text=text[:pos]+appendix+text[pos:]
    assert '\u2014' not in text
    (PAPER/'paper.tex').write_text(text)
    shutil.copy2(Path(__file__).with_name('extension_methods.tex'),PAPER/'extension_methods.tex')
    bib=(PAPER/'references.bib').read_text()
    bib+=r'''
@inproceedings{tong2022videomae,
 author={Tong, Zhan and Song, Yibing and Wang, Jue and Wang, Limin},
 title={{VideoMAE}: Masked Autoencoders Are Data-Efficient Learners for Self-Supervised Video Pre-Training},
 booktitle={Advances in Neural Information Processing Systems},
 year={2022}, url={https://arxiv.org/abs/2203.12602}}
@inproceedings{farneback2003two,
 author={Farneb{\"a}ck, Gunnar},
 title={Two-Frame Motion Estimation Based on Polynomial Expansion},
 booktitle={Image Analysis}, pages={363--370}, year={2003},
 doi={10.1007/3-540-45103-X_50}}
'''
    (PAPER/'references.bib').write_text(bib)
    print('EXTENSION_PAPER_GENERATED',flush=True)

if __name__=='__main__':main()
