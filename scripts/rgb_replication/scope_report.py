"""Separate observed preparation, production wall time, and measured stage time."""
import datetime as dt
import os
import platform
from pathlib import Path
from audit_recovery import OUT,read,save

def main():
    names=['RGB','BGR','RGB_CTX1','RGB_CTX8']
    extraction={n:read(OUT/f'extraction_{n}_complete.json') for n in names}
    finish=max((OUT/f'extraction_{n}_complete.json').stat().st_mtime for n in names)
    fits=[read(p) for p in (OUT/'predictions').glob('*.json')]
    fit_seconds=sum(p['elapsed_seconds'] for p in fits)
    profiles={n:read(OUT/f'profile_{n}.json') for n in ('RGB','BGR')}
    report={'scope':'25 original central identities; all five 16-pair RGB/BGR conditions; native 1/8-pair RGB on L0/L4; layers 4/10/19 retained',
      'preparation_start_approximate_utc':'2026-09-11T11:18:00Z',
      'first_fully_validated_RGB_profile_utc':'2026-09-11T11:55:12Z',
      'preparation_and_validation_minutes_approximate':37.2,
      'production_dispatch_utc':'2026-09-11T11:59:24Z',
      'production_extraction_finished_utc':dt.datetime.fromtimestamp(finish,dt.timezone.utc).isoformat(),
      'production_dispatch_to_extraction_finish_seconds':finish-dt.datetime(2026,9,11,11,59,24,tzinfo=dt.timezone.utc).timestamp(),
      'new_target_forwards':sum(r['rows'] for r in extraction.values()),
      'new_predictions':sum(len(r['cells']) for r in fits),
      'measured_extraction':extraction,'sum_extraction_stage_seconds':sum(r['seconds'] for r in extraction.values()),
      'sum_fitting_seconds':fit_seconds,'timing_notes':'Extraction stages exclude checkpoint loading; dispatch-to-finish wall time includes loads and BGR profiling. CPU fits overlap extraction. Preparation includes artifact recovery, downloads, environment setup, and validation, not just GPU computation. Manuscript integration and clean-room packaging occur afterward.',
      'runtime':read(OUT/'runtime_validation.json'),
      'cpu':'AMD Ryzen 9 9950X3D, 16 cores / 32 logical processors',
      'installed_ram_nominal_GiB':64,'Windows_reported_physical_memory_bytes':66094223360,'wsl_visible_logical_cpus':os.cpu_count(),
      'wsl_meminfo':Path('/proc/meminfo').read_text().splitlines()[:3],
      'peak_allocated_GPU_bytes':max(p['maximum_gpu_allocated_bytes'] for p in profiles.values()),
      'GPU_memory_note':'PyTorch peak allocated tensors during profiling; excludes driver/display allocations and reserved allocator capacity.',
      'scope_projection_before_outcomes':{'RGB_seconds_per_uncached_window':profiles['RGB']['mean_uncached_window_seconds'],
        'primary_RGB_windows':2375,'same_runtime_BGR_windows':2375,'one_pair_windows':950,'eight_pair_windows':950,
        'one_pair_seconds':profiles['RGB']['short_context_seconds']['1'],'eight_pair_seconds':profiles['RGB']['short_context_seconds']['8'],
        'headroom_fraction':.2,'reserved_scoring_validation_seconds':900},
      'completed':['Full input/prediction recovery','Corrected RGB primary and secondary depth panel','Same-runtime BGR replay','Current and matched-history pixels','Native 1/8-pair contexts','Exact historical statistics reconstruction','Whole-identity paired uncertainty'],
      'not_run':['Fresh captures or independent cohort','Additional layouts/speeds/entities/checkpoints','Continuous-cache inference','Nonlinear probes','Tokenizer-embedding history probe'],
      'not_run_reason':'Outside the fixed follow-up scope; the tokenizer-embedding option was not implementation-ready and was not selected.',
      'external_publication':'None; local artifacts only'}
    save(OUT/'scope_runtime_report.json',report)
    print('RUNTIME_REPORT',round(report['production_dispatch_to_extraction_finish_seconds']/60,2),'wall minutes',flush=True)

if __name__=='__main__':
    main()
