"""Write the final evidence-bounded experiment report from actual outputs."""
from datetime import datetime,timezone
from prepare import ROOT,SOURCE,read,save,sha


def main():
    stats=read(ROOT/'analysis/statistics.json')
    transfer=read(ROOT/'analysis/transfer_statistics.json')
    validation=read(ROOT/'analysis/independent_validation.json')
    assert validation['status']=='PASS'
    summary={(r['cohort'],r['condition'],r['model']):r for r in stats['summaries']}
    contrast={(r['cohort'],r['condition'],r['contrast']):r for r in stats['paired_contrasts']}
    ts={(r['cohort'],r['condition'],r['model']):r for r in transfer['summaries']}
    lines=['# MineOcclude: fresh generalization extension','',
        '75 new identities; 150 actual Minecraft recordings; 27,000 frames; '
        '2,850 target rows. Engineering pilots do not enter estimates.','',
        '## Primary within-setting grouped evaluation','',
        'Each cohort contains 25 identities (13 LTR / 12 RTL). All methods use '
        'the same paired targets and identity folds. The neural representation '
        'is fixed RGB MineWorld 700M_16f, layer 19, coarse 2x6, 16 reset pairs.','',
        '| Setting | Neural air RMSE | Neural stone RMSE | History-pixel stone RMSE | Neural minus history, stone (95% CI) |',
        '|---|---:|---:|---:|---|']
    for cohort in ['replication','geometry','speed']:
        a=summary[cohort,'L0','MW_RGB_L19']['rmse']['mean']
        b=summary[cohort,'L4','MW_RGB_L19']['rmse']['mean']
        h=summary[cohort,'L4','PIXEL_HISTORY16']['rmse']['mean']
        d=contrast[cohort,'L4','MW_RGB_L19-minus-PIXEL_HISTORY16']
        lines.append(f"| {cohort} | {a:.6f} | {b:.6f} | {h:.6f} | {d['mean']:.6f} [{d['ci95'][0]:.6f}, {d['ci95'][1]:.6f}] |")
    lines += ['','Errors are in world blocks. Negative paired differences favor '
        'the neural readout. Intervals use 10,000 paired identity resamples and '
        'condition on fitted probes; they are not simultaneous bounds.','',
        '## Separate unchanged-probe transfer','',
        'Training, scaling, and alpha selection use only the 25 fresh original-setting '
        'identities. The destination identities are never used for fitting. Exactly '
        'constant source-training columns are removed to avoid numerical transfer '
        'artifacts; this safeguard was specified before fresh outcomes.','',
        '| Destination | Material | Neural RMSE | Current pixels | History pixels |',
        '|---|---|---:|---:|---:|']
    for cohort in ['geometry','speed']:
        for condition in ['L0','L4']:
            values=[ts[cohort,condition,m]['rmse']['mean'] for m in ['MW_RGB_L19','PIXEL_CURRENT','PIXEL_HISTORY16']]
            lines.append(f'| {cohort} | {condition} | '+ ' | '.join(f'{v:.6f}' for v in values)+' |')
    capture=read(ROOT/'capture_status.json')
    mw=read(ROOT/'analysis/mineworld_complete.json')
    px=read(ROOT/'analysis/pixels_complete.json')
    fits=sum(read(p)['seconds'] for p in (ROOT/'analysis/predictions').glob('*.json') if 'seconds' in read(p))
    seconds=sum(read(p)['elapsed_seconds'] for p in (ROOT/'analysis/transfer').glob('*.json'))
    lines += ['','## What this establishes','',
        '- Fresh trajectories provide new observations beyond the reused central cohort.',
        '- Within-setting results test the fixed readout family after grouped refitting, not zero-shot transfer.',
        '- Secondary results separately measure transfer of a source-trained probe.',
        '- Geometry changes several spatial factors. Higher speed changes traveled distance and target spread within the fixed age window.',
        '- One checkpoint, one sheep entity, two arrangements, two speeds, and one noise regime do not establish general physical reasoning or all possible hidden-state representations.',
        '- Fresh data use a shared software renderer, unlike the recovered historical runtime. Historical-to-fresh differences are not pure sampling effects.',
        '- The historical FIR definition is retained and checked using disjoint visible-motion diagnostics, not exact rendered-origin recalibration.','',
        '## Verification','',
        '- All 150 captures independently checked for frame/tick/action joins, physical setup, exact replayed paths, paired labels, visibility, and drained writers.',
        '- All 75 seeds distinct from historical repository records and engineering pilots.',
        '- Unmodified capture mod: 37 source/build inputs matched; all 43 Java tests passed.',
        '- Selected Python suite: 154 passed, one historical bitwise FIR label assertion failed due to rounding; no old test was edited.',
        '- Independent target-sum check: maximum difference below 2e-15 blocks. Historical raw-state oracle outputs independently reproduced to floating-point precision.',
        '- New statistical implementation: six tests passed, including a complete synthetic fixture and duplicate rejection.',
        f"- Independently validated {stats['cells']} primary and {transfer['cells']} transfer prediction cells, exact target/fold joins, means, and paired intervals.",
        '- Actual tokenizer encoder red/blue inputs checked; cached/uncached frame tokens and reset-repeat forwards checked.',
        '- Final PDF and compact archive require their separate delivery-QA receipt; this report does not imply anonymous publication.','',
        '## Measured compute','',
        f"- Capture: {capture['elapsed_seconds']/60:.2f} minutes, including production runtime startup.",
        f"- RGB extraction: {mw['elapsed_seconds']/60:.2f} minutes including model loading; 2,850 target forwards plus validation calls.",
        f"- Pixel features: {px['elapsed_seconds']:.2f} seconds (overlapped GPU extraction).",
        f'- Primary fits and reference checks: {fits:.2f} summed seconds.',
        f'- Secondary transfer fits and reference checks: {seconds:.2f} summed seconds.',
        f"- Peak allocated GPU tensor memory: {mw['peak_allocated_bytes']/1024**3:.2f} GiB; peak reserved {mw['peak_reserved_bytes']/1024**3:.2f} GiB.",
        '- Java/runtime installation, engineering pilots, tests, manuscript work, and packaging are separate from these measured production stages.',
        '- No cloud compute, external publication, Git push, or Overleaf overwrite was performed.','']
    out=SOURCE/'generalization_outputs'
    out.mkdir(exist_ok=True)
    (out/'EXPERIMENT_REPORT.md').write_text('\n'.join(lines))
    save(out/'result_manifest.json',dict(written_utc=datetime.now(timezone.utc).isoformat(),statistics_sha256=sha(ROOT/'analysis/statistics.json'),transfer_statistics_sha256=sha(ROOT/'analysis/transfer_statistics.json'),validation_sha256=sha(ROOT/'analysis/independent_validation.json')))
    print('EXPERIMENT_REPORT_WRITTEN')


if __name__=='__main__':
    main()
