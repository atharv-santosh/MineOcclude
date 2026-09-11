import numpy as np

def bootstrap(values,strata,seed=94113,draws=10000):
    v=np.asarray(values,dtype=float)
    assert len(v)==len(strata) and np.isfinite(v).all()
    rng=np.random.default_rng(seed)
    totals=np.zeros(draws)
    for s in sorted(set(strata)):
        indices=np.array([i for i,x in enumerate(strata) if x==s])
        chosen=rng.integers(0,len(indices),size=(draws,len(indices)))
        totals += v[indices[chosen]].sum(1)
    return dict(mean=float(v.mean()),ci=np.quantile(totals/len(v),[.025,.975]).tolist())

def family_scores(cells,lo,hi):
    grouped={}
    for r in cells:
        if lo<=r['age']<=hi:
            grouped.setdefault(r['family_id'],{}).setdefault(r['variant'],[]).append(r)
    result={}
    for f,variants in sorted(grouped.items()):
        assert set(variants)=={0,1}
        rmses=[];maes=[]; preds=[]; targets=[]
        for variant in [0,1]:
            rs=sorted(variants[variant],key=lambda r:r['age'])
            assert [r['age'] for r in rs]==list(range(lo,hi+1))
            p=np.array([r['prediction'] for r in rs]);y=np.array([r['target'] for r in rs])
            rmses.append(np.sqrt(np.mean((p-y)**2)));maes.append(np.mean(abs(p-y)))
            preds.append(p);targets.append(y)
        dy=targets[1]-targets[0];dp=preds[1]-preds[0]
        valid=abs(dy)>1e-12
        first=variants[0][0]
        result[f]=dict(rmse=float(np.mean(rmses)),mae=float(np.mean(maes)),contrast_rmse=float(np.sqrt(np.mean((dp-dy)**2))),sign_agreement=float(np.mean(np.sign(dp[valid])==np.sign(dy[valid]))) if valid.any() else None,layout=first['layout'],family=first['family'])
    return result

def summarize_motion(cells):
    groups={}
    for r in cells:groups.setdefault((r['model'],r['source'],r['condition']),[]).append(r)
    result=[];scores={}
    for key,rs in sorted(groups.items()):
        for lo,hi in [(1,10),(11,15),(16,19),(1,19)]:
            fs=family_scores(rs,lo,hi);scores[key+(lo,hi)]=fs
            for layout in ['pooled','layout_01','layout_04']:
                keep=[v for v in fs.values() if layout=='pooled' or v['layout']==layout]
                strata=[v['layout']+'/'+v['family'] for v in keep]
                summary={k:bootstrap([v[k] for v in keep],strata) for k in ['rmse','mae','contrast_rmse']}
                valid=[v for v in keep if v['sign_agreement'] is not None]
                summary['sign_agreement']=bootstrap([v['sign_agreement'] for v in valid],[v['layout']+'/'+v['family'] for v in valid]) if valid else None
                result.append(dict(model=key[0],source=key[1],condition=key[2],ages=[lo,hi],layout=layout,families=len(keep),**summary))
    differences=[]
    for (model,source,condition,lo,hi),fs in sorted(scores.items()):
        if model!='MW_700M' or source!=condition:continue
        for baseline in ['PIXEL_HISTORY16','VIDEOMAE_S','FRAME_DIFF16','FLOW16','META_LINEAR','META_CUBIC','META_FAMILY','ORACLE_LAST','ORACLE_CV']:
            bs='METADATA' if baseline.startswith(('META','ORACLE')) else condition
            other=scores.get((baseline,bs,condition,lo,hi))
            if other is None:continue
            assert set(fs)==set(other)
            for layout in ['pooled','layout_01','layout_04']:
                ids=[i for i in fs if layout=='pooled' or fs[i]['layout']==layout]
                diff=[fs[i]['rmse']-other[i]['rmse'] for i in ids]
                strata=[fs[i]['layout']+'/'+fs[i]['family'] for i in ids]
                differences.append(dict(model=model,baseline=baseline,condition=condition,ages=[lo,hi],layout=layout,interpretation='negative favors MineWorld',**bootstrap(diff,strata)))
    return dict(summaries=result,paired_differences=differences,bootstrap_draws=10000,bootstrap_seed=94113,unit='independent paired-variant family',stratification='layout and motion type')
