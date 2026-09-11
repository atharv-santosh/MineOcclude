"""Isolated 1.16.5 runtime using official Mojang/Fabric artifacts and built mod."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path('/home/bpcfno/mineocclude-generalization-20260911')
SOURCE = Path(__file__).resolve().parents[2]
SERVER, CLIENT = ROOT/'server', ROOT/'client'


def digest(path, algorithm='sha1'):
    h = hashlib.new(algorithm)
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def fetch(url, path, expected=None, algorithm='sha1'):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (not expected or digest(path, algorithm) == expected):
        return path
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r, path.with_suffix(path.suffix+'.partial').open('wb') as f:
                shutil.copyfileobj(r, f)
            temp = path.with_suffix(path.suffix+'.partial')
            if expected and digest(temp, algorithm) != expected:
                raise ValueError(f'Hash mismatch: {url}')
            temp.replace(path)
            return path
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2**attempt)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding='utf-8')


def main():
    for d in [SERVER, CLIENT, SERVER/'mods', CLIENT/'mods']:
        d.mkdir(parents=True, exist_ok=True)
    installer = fetch('https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.1/fabric-installer-1.0.1.jar', ROOT/'fabric-installer.jar', '62edf170bdcc41edea85d33acf3eb85474258699b3d41f9418d286c836cb088d', 'sha256')
    if not (SERVER/'fabric-server-launch.jar').exists():
        subprocess.run(['java','-jar',str(installer),'server','-mcversion','1.16.5','-loader','0.15.11','-downloadMinecraft'], cwd=SERVER, check=True)
    assert digest(SERVER/'server.jar','sha256') == '58f329c7d2696526f948470aa6fd0b45545039b64cb75015e64c12194b373da6'
    versions = json.loads(fetch('https://piston-meta.mojang.com/mc/game/version_manifest_v2.json', ROOT/'versions.json').read_text())
    version = next(v for v in versions['versions'] if v['id']=='1.16.5')
    info = json.loads(fetch(version['url'], ROOT/'minecraft-1.16.5.json',version['sha1']).read_text())
    classpath = []
    for lib in info['libraries']:
        allowed = not lib.get('rules')
        for rule in lib.get('rules',[]):
            if rule.get('os',{}).get('name','linux') == 'linux':
                allowed = rule['action']=='allow'
        if not allowed:
            continue
        dl = lib.get('downloads',{})
        if 'artifact' in dl:
            a=dl['artifact']
            classpath.append(fetch(a['url'], CLIENT/'libraries'/a['path'], a['sha1']))
        classifier=lib.get('natives',{}).get('linux')
        if classifier:
            a=dl['classifiers'][classifier.replace('${arch}','64')]
            archive=fetch(a['url'],CLIENT/'libraries'/a['path'],a['sha1'])
            with zipfile.ZipFile(archive) as z:
                for m in z.infolist():
                    if m.is_dir() or m.filename.startswith('META-INF/'):
                        continue
                    dest=(CLIENT/'natives'/m.filename).resolve()
                    assert dest.is_relative_to((CLIENT/'natives').resolve())
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(m) as src,dest.open('wb') as out:
                        shutil.copyfileobj(src,out)
    profile=json.loads(fetch('https://meta.fabricmc.net/v2/versions/loader/1.16.5/0.15.11/profile/json',ROOT/'fabric-profile.json').read_text())
    for lib in profile['libraries']:
        group,artifact,version=lib['name'].split(':')
        rel=Path(*group.split('.'))/artifact/version/f'{artifact}-{version}.jar'
        classpath.append(fetch(lib.get('url','https://maven.fabricmc.net/')+rel.as_posix(),CLIENT/'libraries'/rel,lib.get('sha1')))
    a=info['downloads']['client']
    jar=fetch(a['url'],CLIENT/'versions/1.16.5/1.16.5.jar',a['sha1'])
    assert digest(jar,'sha256')=='00b5ebbc33e95ea88c1ab80601599c9827e9aa861d93ccc2cfcbbfd996e86263'
    classpath.append(jar)
    write(CLIENT/'classpath.txt','\n'.join(map(str,classpath))+'\n')
    ai=info['assetIndex']
    assets=json.loads(fetch(ai['url'],CLIENT/'assets/indexes/1.16.json',ai['sha1']).read_text())
    def asset(a):
        h=a['hash']
        fetch(f'https://resources.download.minecraft.net/{h[:2]}/{h}',CLIENT/'assets/objects'/h[:2]/h,h)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(asset,assets['objects'].values()))
    a=info['logging']['client']['file']
    fetch(a['url'],CLIENT/'assets/log_configs'/a['id'],a['sha1'])
    api=fetch('https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/0.42.0+1.16/fabric-api-0.42.0+1.16.jar',ROOT/'fabric-api.jar')
    pom=fetch('https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/0.42.0+1.16/fabric-api-0.42.0+1.16.pom',ROOT/'fabric-api.pom')
    ns={'m':'http://maven.apache.org/POM/4.0.0'}
    apis=[api]
    for dep in ET.parse(pom).getroot().findall('.//m:dependencies/m:dependency',ns):
        if dep.findtext('m:groupId',namespaces=ns)!='net.fabricmc.fabric-api':
            continue
        artifact=dep.findtext('m:artifactId',namespaces=ns)
        version=dep.findtext('m:version',namespaces=ns)
        filename=f'{artifact}-{version}.jar'
        apis.append(fetch(f'https://maven.fabricmc.net/net/fabricmc/fabric-api/{artifact}/{version}/{filename}',ROOT/'api-components'/filename))
    mod=ROOT/'mod/build/libs/mineocclude-0.1.1.jar'
    assert mod.is_file(), 'Build the frozen mod first'
    for root in [SERVER,CLIENT]:
        shutil.copy2(api,root/'mods/fabric-api-0.42.0+1.16.jar')
        for part in apis[1:]:
            shutil.copy2(part,root/'mods'/part.name)
        shutil.copy2(mod,root/'mods/mineocclude-0.1.1.jar')
    props=(SOURCE/'fabric/mineocclude-mod/provisioning/person-c-c1-v0_2/server.properties').read_text()
    props='\n'.join(x for x in props.splitlines() if not x.startswith(('server-ip=','server-port=','online-mode=')))
    write(SERVER/'server.properties',props+'\nserver-ip=127.0.0.1\nserver-port=25575\nonline-mode=false\n')
    write(SERVER/'eula.txt','eula=true\n')
    shutil.copy2(SOURCE/'fabric/mineocclude-mod/provisioning/person-c-c1-v0_2/client-options.txt', CLIENT/'options.txt')
    config=dict(runtime_root=str(ROOT),server_root=str(SERVER),client_root=str(CLIENT),java_executable='/usr/bin/java',output_root=str(ROOT/'logs'),display_strategy='XVFB',display=':107',xvfb_executable='/usr/bin/Xvfb',mesa_software_rendering=True,server_max_heap='2G',client_max_heap='2G',server_start_timeout_seconds=300,client_start_timeout_seconds=300,extra_environment={'MINEOCCLUDE_AUTOCONNECT':'127.0.0.1:25575','MINEOCCLUDE_AUTOCONNECT_DELAY_MS':'5000','LP_NUM_THREADS':'4'})
    write(ROOT/'runtime.json',json.dumps(config,indent=2)+'\n')
    pins={str(p.relative_to(ROOT)):digest(p,'sha256') for p in [mod,api,jar,SERVER/'server.jar',installer]}
    write(ROOT/'artifact_hashes.json',json.dumps(pins,indent=2)+'\n')
    print('PROVISIONED',pins,flush=True)


if __name__=='__main__':
    main()
