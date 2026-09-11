"""Deliver separate, verified paper and reproduction artifacts."""
from diag_common import *
import argparse
import shutil
import subprocess
import zipfile

DEST=SOURCE/'history_diagnostic_outputs'
PAPER=DEST/'paper'
DELIVERY=SOURCE/'output/pdf'
OLD={
    'mineocclude_generalization.pdf':'bb010e63965580bae63c277a1c69de1b71dda3ad83486f64043299b57fd9fb28',
    'paper_generalization.tex':'ba75c2c62c9234077953fb2411986c6d0f716f57583da91fcaf17153874ba7e0',
}


def archive(folder,path,files):
    assert not path.exists(),path
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(files):
            assert p.is_relative_to(folder)
            z.write(p,p.relative_to(folder).as_posix())
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(set(z.namelist()))
        for name in z.namelist():
            assert '..' not in Path(name).parts and not Path(name).is_absolute()
    return dict(file=path.name,bytes=path.stat().st_size,sha256=sha(path))


def report():
    out=ROOT/'analysis'
    assert read(out/'independent_validation.json')['status']=='PASS'
    assert read(out/'comparator_replay_validation.json')['status']=='PASS'
    s=read(out/'statistics.json')
    def rmse(m,phase='correct',layout='pooled',setting='native',c='L4'):
        return next(r['rmse'] for r in s['summaries'] if (r['model'],r['phase'],r['layout'],r['setting'],r['condition'],r['ages'])==(m,phase,layout,setting,c,'1-10'))
    def val(v):
        return f"{v['mean']:.3f} [{v['ci95'][0]:.3f}, {v['ci95'][1]:.3f}]"
    text=['# MineOcclude prospective diagnostic: verified findings','',
        'New captures and analyses, not a relabeling of the previous experiments. Primary interval: occlusion ages 1–10. 48 training and 48 held-out identities, two layouts, 192 paired recordings. The earlier central and 75-identity extension studies are preserved separately.','',
        '## Correct-history hidden-position decoding','',
        '| Predictor | Mean identity RMSE [95% bootstrap interval], blocks |',
        '|---|---|']
    for m in ['MW_700M','MW_300M','MW_700M_MLP','MW_300M_MLP','PIXEL_CURRENT','PIXEL_HISTORY16','IMAGE_TRACKER_CV','DIRECTION_AGE','ORACLE_LAST_SEEN','ORACLE_CONSTANT_VELOCITY','TRAINING_MEAN']:
        text.append(f'| {m} | {val(rmse(m))} |')
    opt=read(out/'optimizer_check/statistics.json')
    text+=['','A separate training-diagnostic-triggered check extends only the final MLP optimization budget, without reopening hyperparameter selection. All 24 seed-level fits converge; the original capped fits remain above.','']
    for m in ['MW_700M_MLP_OPT10K','MW_300M_MLP_OPT10K']:
        r=next(r for r in opt['summaries'] if r['model']==m and r['condition']=='L4' and r['phase']=='correct' and r['layout']=='pooled' and r['ages']=='1-10')
        text.append(f'- {m}: {val(r["rmse"])}.')
    contrast=next(r['rmse_difference'] for r in s['paired_contrasts'] if r['first']=='MW_700M' and r['second']=='PIXEL_HISTORY16' and r['condition']=='L4' and r['layout']=='pooled' and r['ages']=='1-10')
    text+=['',f'The paired 700M ridge minus history-pixel difference is {val(contrast)}. Its interval includes zero; this new pooled comparison does not establish a reliable advantage. Direction-and-age remains much more accurate despite variable commanded speeds.','']
    text+=['','## History interventions','',
        'Current image and actions are fixed; only the earlier images change. Differences below are intervened minus correct-history RMSE, using reciprocal-donor-pair bootstrap intervals. Positive means worse after intervention.','',
        '| Predictor | Swapped history | Repeated-current history |','|---|---|---|']
    for m in ['MW_700M','MW_300M','MW_700M_MLP','MW_300M_MLP','PIXEL_CURRENT','PIXEL_HISTORY16','IMAGE_TRACKER_CV']:
        rows=[next(r['rmse_difference'] for r in s['interventions'] if r['model']==m and r['layout']=='pooled' and r['ages']=='1-10' and r['phase']==p) for p in ['swapped','removed']]
        text.append(f'| {m} | {val(rows[0])} | {val(rows[1])} |')
    text+=['','## Geometry transfer','',
        'Source training uses only the original layout. Visible calibration fits one affine output correction on six predesignated destination-training air identities. Destination hidden test labels never fit the calibration.','',
        '| Predictor | Frozen air / stone | Visible-calibrated air / stone | Native air / stone |','|---|---|---|---|']
    for m in ['MW_700M','MW_300M','PIXEL_CURRENT','PIXEL_HISTORY16']:
        cells=[]
        for setting in ['frozen_transfer','visible_calibrated_transfer','native']:
            cells.append(' / '.join(f"{rmse(m,layout='layout_04',setting=setting,c=c)['mean']:.3f}" for c in ['L0','L4']))
        text.append('| '+m+' | '+' | '.join(cells)+' |')
    text+=['','## Validation and remaining limits','',
        '- Saved-fit replay, split/target joins, source-provenance checks, independent arithmetic, and intervention resampling checks passed for all 40,128 original prediction cells. The separate converged-MLP check adds 7,296 replayed cells and a CPU statistics rebuild.',
        '- One validation assertion incorrectly assumed every prior frame preceding the selected consecutive occlusion segment was visible. A recorded transient occlusion violated that shortcut. Validation now uses exact recorded visibility; the failed check and repair are preserved, and no identity, prediction, target, or original statistic changed.',
        '- Swapping history changes predictions but does not reliably make them follow donor position: 700M donor-direction agreement is 32.1%. Removing history worsens decoding. These are distinct findings.',
        '- The image tracker falls back to the training mean on 59.4% of primary stone rows. Its weak score must be interpreted alongside this limited observation coverage.',
        '- Statistics condition on fitted models; intervals do not include retraining uncertainty or multiple-comparison adjustment.',
        '- Two sizes of one pretrained family are not two independent architectures. One entity and one stochastic motion family remain.',
        '- History swaps are input-distribution interventions, not proof of a neural memory circuit. Image-history matching does not match resolution or pretraining.',
        '- Full tracker coverage, later-age bins, nonlinear optimizer diagnostics, and all unfavorable results remain in the snapshot.',
        '- Anonymous release and access are separate from local verification. Check the delivery receipt for their actual status.','']
    (DEST/'VERIFIED_FINDINGS.md').write_text('\n'.join(text))
    print('FINDINGS_REPORT_WRITTEN',flush=True)


def deliver():
    assert read(ROOT/'analysis/analysis_complete.json')['status']=='PASS'
    assert read(ROOT/'analysis/comparator_replay_validation.json')['status']=='PASS'
    assert read(DEST/'paper_visual_qa.json')['status']=='PASS'
    assert read(DEST/'clean_cpu_reproduction.json')['status']=='PASS'
    assert read(DEST/'raw_zip_crc_validation.json')['status']=='PASS'
    for name,h in OLD.items():
        assert sha(DELIVERY/name)==h,('Earlier delivery changed',name)
    DELIVERY.mkdir(parents=True,exist_ok=True)
    pdf=DELIVERY/'mineocclude_history_diagnostic.pdf'
    tex=DELIVERY/'paper_history_diagnostic.tex'
    assert not pdf.exists() and not tex.exists()
    shutil.copy2(PAPER/'paper.pdf',pdf); shutil.copy2(PAPER/'paper.tex',tex)
    files=[p for p in PAPER.iterdir() if p.suffix in ('.tex','.bib','.sty','.pdf','.png') and p.name!='paper.pdf']
    overleaf=archive(PAPER,DELIVERY/'mineocclude_history_diagnostic_overleaf.zip',files)
    snap=DEST/'anonymous_reproduction'
    for name,h in read(snap/'SNAPSHOT_SHA256.json').items():
        assert sha(snap/name)==h,('Snapshot changed',name)
    reproduction=archive(snap,DELIVERY/'mineocclude_history_diagnostic_reproduction.zip',[p for p in snap.rglob('*') if p.is_file() and '__pycache__' not in p.parts])
    repo_status=read(DEST/'anonymous_access_status.json')
    receipt=dict(status='DELIVERED_LOCALLY',main_text_pages=8,pdf=dict(file=pdf.name,bytes=pdf.stat().st_size,sha256=sha(pdf)),tex=dict(file=tex.name,sha256=sha(tex)),overleaf=overleaf,reproduction=reproduction,raw=read(DEST/'raw_archive_receipt.json'),optional_fitted_readouts=read(DEST/'fitted_readouts_receipt.json'),anonymous_access=repo_status,prior_deliveries_preserved=OLD,validation_sha256=sha(ROOT/'analysis/independent_validation.json'),clean_cpu_receipt_sha256=sha(DEST/'clean_cpu_reproduction.json'),visual_qa_sha256=sha(DEST/'paper_visual_qa.json'))
    save(DELIVERY/'history_diagnostic_delivery_manifest.json',receipt)
    shutil.copy2(DEST/'VERIFIED_FINDINGS.md',DELIVERY/'history_diagnostic_verified_findings.md')
    print('NEW_DELIVERY_READY',json.dumps(receipt,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['report','deliver']); a=p.parse_args()
    {'report':report,'deliver':deliver}[a.mode]()
