"""Full-suite runners must install the dependencies of collected desktop tests."""
from pathlib import Path
import re
import shlex

import pytest


ROOT = Path(__file__).resolve().parents[1]


def requirement_names(path, seen=None):
    seen = set() if seen is None else seen
    path = path.resolve()
    assert path.is_relative_to(ROOT)
    if path in seen:
        return set()
    seen.add(path)
    names = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith('-r '):
            names |= requirement_names(path.parent / line[3:].strip(), seen)
        elif line and not line.startswith('#'):
            match = re.match(r'[A-Za-z0-9_.-]+', line)
            assert match, 'Unsupported dependency declaration'
            names.add(re.sub(r'[-_.]+', '-', match.group()).lower())
    return names


@pytest.mark.parametrize('job', ['sqlite-tests', 'mysql-tests'])
def test_full_suite_ci_installs_collected_desktop_dependencies(job):
    workflow = (ROOT / '.github/workflows/backend-tests.yml').read_text()
    section = workflow.split(f'  {job}:\n', 1)[1]
    section = re.split(r'(?m)^  [a-z][a-z0-9-]*:\s*$', section)[0]
    installed = set()
    for command in re.findall(r'run: python -m pip install ([^\n]+)', section):
        args = shlex.split(command)
        for index, arg in enumerate(args):
            if arg == '-r':
                installed |= requirement_names(ROOT / args[index + 1])
    assert {'customtkinter', 'pillow', 'xlsxwriter'} <= installed, (
        'The full suite collects headless OfflineApplication tests; install '
        'their desktop dependency closure without skipping those tests.'
    )
