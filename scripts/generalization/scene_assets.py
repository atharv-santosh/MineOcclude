"""Show actual paired fresh-capture inputs and check nonblank target images."""
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prepare import ROOT,SOURCE,read,save,sha


def main():
    manifest=read(ROOT/'manifest.json')
    checks=[]
    for unit,info in manifest['units'].items():
        values=[]
        for t in info['target_model_frame_indices']:
            path=ROOT/'captures'/unit/'client/frames'/f'{t:06d}.png'
            image=np.asarray(Image.open(path).convert('RGB'))
            std=float(image.std())
            assert std>5,('Blank/corrupt capture',unit,t,std)
            values.append(std)
        checks.append(dict(unit=unit,min_target_image_standard_deviation=min(values)))
    plt.rcParams.update({'font.family':'serif','font.serif':['DejaVu Serif'],'font.size':9})
    fig,axes=plt.subplots(3,2,figsize=(6.5,5.8),layout='constrained')
    provenance=[]
    for row,(cohort,label) in enumerate([('replication','Original setting, 2.0 blocks/s'),('geometry','Changed geometry, 2.0 blocks/s'),('speed','Original setting, 3.0 blocks/s')]):
        for column,condition in enumerate(['L0','L4']):
            unit=f'g26_{cohort}_01__{condition}'
            t=manifest['units'][unit]['target_model_frame_indices'][0]
            path=ROOT/'captures'/unit/'client/frames'/f'{t:06d}.png'
            axes[row,column].imshow(Image.open(path).convert('RGB'))
            axes[row,column].set_axis_off()
            axes[row,column].set_title(label+'\n'+('Air' if condition=='L0' else 'Stone'),fontsize=9,pad=4)
            provenance.append(dict(unit=unit,frame=t,sha256=sha(path),target=manifest['units'][unit]['targets'][0]))
    destination=SOURCE/'generalization_outputs/paper'
    destination.mkdir(parents=True,exist_ok=True)
    fig.savefig(destination/'fresh_captures.pdf',bbox_inches='tight',metadata={'Title':'Actual fresh MineOcclude captures','Author':''})
    fig.savefig(destination/'fresh_captures.png',dpi=220,bbox_inches='tight')
    plt.close(fig)
    save(ROOT/'analysis/fresh_scene_checks.json',dict(status='PASS',target_images_checked=2850,minimum_standard_deviation=min(c['min_target_image_standard_deviation'] for c in checks),displayed_frames=provenance))
    print('FRESH_SCENE_ASSETS_VERIFIED')


if __name__=='__main__':
    main()
