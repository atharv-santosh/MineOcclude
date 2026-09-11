from common import *
import shutil
import socket

def main():
    config=read(ROOT/'runtime.json')
    destination=ROOT/'capture_worker1'
    assert destination.resolve().is_relative_to(ROOT.resolve()) and not destination.exists()
    with socket.socket() as check:check.bind(('127.0.0.1',25576))
    assert not Path('/tmp/.X108-lock').exists()
    destination.mkdir()
    excluded={'logs','mineocclude_out','mineocclude_client_out','mineocclude_motion_schedules','mineocclude_schedules'}
    for kind in ['client','server']:
        source=Path(config[kind+'_root']);target=destination/kind
        shutil.copytree(source,target,ignore=shutil.ignore_patterns(*excluded))
        config[kind+'_root']=str(target)
    properties=destination/'server/server.properties'
    body=properties.read_text();assert 'server-port=25575' in body
    properties.write_text(body.replace('server-port=25575','server-port=25576').replace('rcon.port=25575','rcon.port=25576'))
    cp=destination/'client/classpath.txt'
    old=read(ROOT/'runtime.json')['client_root']
    cp.write_text(cp.read_text().replace(old,str(destination/'client')))
    config['runtime_root']=str(destination);config['display']=':108'
    config['extra_environment']['MINEOCCLUDE_AUTOCONNECT']='127.0.0.1:25576'
    config['output_root']=str(ROOT/'parallel_capture_logs')
    save(ROOT/'runtime_worker1.json',config)
    immutable={}
    for kind in ['client','server']:
        for path in (destination/kind).rglob('*.jar'):
            relative=path.relative_to(destination/kind)
            original=Path(read(ROOT/'runtime.json')[kind+'_root'])/relative
            assert sha(path)==sha(original)
            immutable[str(path.relative_to(destination))]=sha(path)
    save(ROOT/'PARALLEL_RUNTIME_PREPARATION.json',dict(status='PREPARED_REQUIRES_FRAME_EQUIVALENCE',independent_port=25576,independent_display=':108',jar_sha256=immutable,original_runtime_unchanged=True))
    print('PARALLEL_RUNTIME_PREPARED',flush=True)

if __name__=='__main__':main()
