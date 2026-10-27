from pathlib import Path
from types import SimpleNamespace

from scripts.build_windows import copy_notices


def test_copying_and_distinct_vendor_notices_are_preserved(tmp_path):
    source=tmp_path/'source'
    files=[Path('package.dist-info/licenses/COPYING.txt'),Path('vendor/a/LICENSE'),Path('vendor/b/LICENSE')]
    for number,file in enumerate(files):
        path=source/file;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(str(number))
    dist=SimpleNamespace(files=files,locate_file=lambda file:source/file,metadata={'Name':'example'})
    destination=tmp_path/'notices'
    copy_notices(dist,destination)
    assert [(destination/'example'/file).read_text() for file in files]==['0','1','2']
