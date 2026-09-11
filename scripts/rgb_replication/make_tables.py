"""Generate manuscript table rows directly from the verified numerical snapshot."""
from audit_recovery import OUT,read

def main():
    s=read(OUT/'summary.json')['summary']
    dest=OUT/'paper'
    def write(name,rows):
        (dest/name).write_text('\n'.join(rows)+'\n',encoding='utf-8')
    rows=[]
    for c in range(5):
        key=f'L{c}'; v=s['MW_RGB_L19'][key]
        values=[v['rmse']['mean'],v['mae']['mean'],v['r2']['mean'],s['PIXEL_CURRENT'][key]['rmse']['mean'],s['PIXEL_HISTORY16'][key]['rmse']['mean']]
        rows.append(key+' & '+' & '.join(f'${x:.3f}$' for x in values)+r' \\')
    write('rgb_condition_rows.tex',rows)
    rows=[]
    for age in ('1-5','6-10','11-15','16-19'):
        values=[s['MW_RGB_L19'][f'L{c}']['age_rmse'][age]['mean'] for c in range(5)]
        rows.append(age.replace('-','--')+' & '+' & '.join(f'${x:.3f}$' for x in values)+r' \\')
    write('rgb_age_rows.tex',rows)
    rows=[]
    for layer in (4,10,19):
        values=[s[f'MW_RGB_L{layer:02d}'][f'L{c}']['rmse']['mean'] for c in range(5)]
        rows.append(str(layer)+' & '+' & '.join(f'${x:.3f}$' for x in values)+r' \\')
    write('rgb_depth_rows.tex',rows)
    rows=[]
    for c in range(5):
        key=f'L{c}'
        values=[s[m][key]['rmse']['mean'] for m in ('LEGACY_MW_CURRENT','MW_BGR_L19','MW_RGB_L19')]
        diff=read(OUT/'summary.json')['paired_differences']['MW_BGR_L19'][key]
        rows.append(key+' & '+' & '.join(f'${x:.3f}$' for x in values)+f" & ${diff['mean']:.3f}$ & $[{diff['ci_low']:.3f},{diff['ci_high']:.3f}]$"+r' \\')
    write('rgb_channel_rows.tex',rows)
    rows=[]
    for n in (1,8,16):
        m='MW_RGB_L19'+(f'_CTX{n}' if n!=16 else '')
        values=[s[m][c]['rmse'] for c in ('L0','L4')]
        rows.append(str(n)+' & '+' & '.join(f"${v['mean']:.3f}$ & $[{v['ci_low']:.3f},{v['ci_high']:.3f}]$" for v in values)+r' \\')
    write('rgb_context_rows.tex',rows)
    print('TABLE_ROWS_REBUILT',flush=True)

if __name__=='__main__':
    main()
