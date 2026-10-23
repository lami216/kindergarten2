"""Fail closed if any installed package is missing, skipped or vulnerable."""
import json
from pathlib import Path
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main(freeze, audit):
    installed = {}
    for line in Path(freeze).read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        req = Requirement(line)
        versions = list(req.specifier)
        if len(versions) != 1 or versions[0].operator != '==':
            raise SystemExit('Runtime freeze must contain exact package versions')
        installed[canonicalize_name(req.name)] = versions[0].version
    if not installed:
        raise SystemExit('Runtime freeze is empty; audit coverage cannot be established')
    result = json.loads(Path(audit).read_text(encoding='utf-8'))
    audited = {canonicalize_name(d['name']): d for d in result['dependencies']}
    errors = []
    for name, version in installed.items():
        row = audited.get(name, {})
        if row.get('version') != version or 'vulns' not in row or row.get('skip_reason'):
            errors.append(f'{name}=={version}: missing or skipped')
        elif row['vulns']:
            errors.append(f'{name}=={version}: vulnerabilities found')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Complete audit: {len(installed)} installed packages, no skips or known vulnerabilities')


if __name__ == '__main__':
    main(*sys.argv[1:])
