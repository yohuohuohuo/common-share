#!/usr/bin/env python3
"""Validate plan documents only. Never invoke product tests or network APIs."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-report', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    plans = root / 'docs/superpowers/plans'
    status = json.loads((plans / 'execution-status.json').read_text())
    coverage = json.loads((plans / 'coverage-map.json').read_text())
    errors: list[str] = []
    files = sorted(root.rglob('*.md'))
    tasks: dict[str, str] = {}
    phase_rows = status['phases']
    if [p['id'] for p in phase_rows] != [f'P{i:02}' for i in range(1, 9)]:
        errors.append('Expected exactly P01 through P08')
    for i, phase in enumerate(phase_rows):
        expected = [] if i == 0 else [phase_rows[i-1]['id']]
        if phase['dependencies'] != expected:
            errors.append(f"Invalid dependency order: {phase['id']}")
        path = plans / phase['plan']
        if not path.is_file():
            errors.append(f'Missing phase plan: {path.name}')
            continue
        text = path.read_text()
        for field in ('**Goal:**', '**Architecture:**', '**Tech Stack:**', '**Spec:**',
                      '## Global Constraints', '## Review Focus',
                      '## 最小阅读与前置检查', '## 本阶段验收与交接', '**停止边界：**'):
            if field not in text:
                errors.append(f'{path.name}: missing {field}')
        for task in re.findall(r'^## (P\d\d\.\d\d)：', text, re.M):
            if task in tasks:
                errors.append(f'Duplicate task owner: {task}')
            tasks[task] = path.name
        if re.search(r'(?i)\bTODO\b|\bTBD\b|实现稍后补|按T01.?T22顺序', text):
            errors.append(f'Placeholder or obsolete execution order: {path.name}')
    expected_tasks = {f'P{i:02}.{j:02}' for i, n in enumerate((4,3,4,3,3,2,2,2),1)
                      for j in range(1,n+1)}
    if set(tasks) != expected_tasks:
        errors.append('Phase-local task inventory differs from 23 expected tasks')
    if set(coverage['legacyTasks']) != {f'T{i:02}' for i in range(1,23)}:
        errors.append('Original T01-T22 coverage incomplete')
    for legacy, targets in coverage['legacyTasks'].items():
        if len(targets) != (2 if legacy == 'T19' else 1):
            errors.append(f'Ambiguous original task owner: {legacy}')
        for target in targets:
            if target not in tasks:
                errors.append(f'Unknown mapped task: {target}')
    for prefix, key, total in [('R','requirements',12),('U','reviewRequirements',6)]:
        if set(coverage[key]) != {f'{prefix}{i:02}' for i in range(1,total+1)}:
            errors.append(f'{prefix} coverage incomplete')
        for name, targets in coverage[key].items():
            for target in targets:
                if target not in tasks and target not in {p['id'] for p in phase_rows}:
                    errors.append(f'{name}: invalid target {target}')
    local_links = 0
    for path in files:
        text = path.read_text()
        if len(re.findall(r'^```', text, re.M)) % 2:
            errors.append(f'Unclosed fenced block: {path.relative_to(root)}')
        for link in re.findall(r'\]\(([^)]+)\)', text):
            if '://' in link or link.startswith(('#','mailto:')):
                continue
            target = unquote(link.split('#',1)[0])
            if not target:
                continue
            local_links += 1
            if not (path.parent / target).resolve().is_file():
                errors.append(f'Broken local link: {path.name} -> {target}')
    for old in ('2026-09-21-jev-gmgn-trader-implementation.md',
                '2026-09-21-reference-review-implementation.md'):
        text = (plans / old).read_text()
        if '不要执行这份旧入口' not in text or len(text) > 1200:
            errors.append(f'Legacy plan still looks executable: {old}')
    result = {
        'revision':'R3', 'scope':'DOCUMENT_VALIDATION_ONLY',
        'sourceCommit':coverage['sourceCommit'], 'phaseCount':len(phase_rows),
        'phaseTaskCount':len(tasks), 'legacyTaskCoverage':22,
        'productRequirementCoverage':12, 'reviewRequirementCoverage':6,
        'markdownFilesChecked':len(files), 'localLinksChecked':local_links,
        'checks':['phase inventory','dependency order','single task owners',
                  'T/R/U mappings','required phase sections','legacy redirects',
                  'local links','balanced fences','placeholder scan'],
        'productCodeImplemented':False, 'productTestsExecuted':False,
        'liveTradesSubmitted':False, 'errors':errors,
    }
    if args.write_report:
        (root / 'document-validation.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        paths = sorted(p for p in root.rglob('*') if p.is_file()
                       and p.name != 'SHA256SUMS.txt' and '.git' not in p.parts)
        (root / 'SHA256SUMS.txt').write_text(''.join(
            f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n'
            for p in paths))
    if not args.write_report and (root / 'SHA256SUMS.txt').exists():
        for line in (root / 'SHA256SUMS.txt').read_text().splitlines():
            digest, name = line.split('  ',1)
            path = root / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                errors.append(f'Checksum mismatch: {name}')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
