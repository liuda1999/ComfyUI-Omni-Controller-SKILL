#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sync the canonical repo workflow library into the skill's live library.

Design (agreed with user, option A + thorough):
  * CANONICAL base  = comfyui-controller/assets/workflow_library.json
    (repo-bundled workflows incl. 6 MiniMax + all legacy node_dependencies;
     git-safe, contains NO personal workflows).
  * LIVE library    = skills/comfyui-controller/assets/workflow_library.json
    (= canonical base + local personal workflows merged in, so the skill that
     loads this file sees everything we inventoried).

Personal entries are added to `workflows` but deliberately NOT to `file_index`,
so the builder's incremental update (compute_file_changes) can never treat them
as "deleted". The canonical base's file_index (repo-relative) is preserved.

Usage:
  python sync_skill_library.py            # merge + write skill library
  python sync_skill_library.py --no-merge # write canonical base only (drop personal)
"""
import json, os, shutil, time, argparse, copy

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))  # .../ComfyUI-Omni-Controller-SKILL
BASE_LIB = os.path.join(REPO_ROOT, 'comfyui-controller', 'assets', 'workflow_library.json')
SKILL_LIB = os.path.join(REPO_ROOT, 'skills', 'comfyui-controller', 'assets', 'workflow_library.json')


def load(p):
    return json.load(open(p, encoding='utf-8'))


def save(p, d):
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-merge', action='store_true',
                    help='只写入规范库（丢弃个人工作流），不做合并')
    args = ap.parse_args()

    base = load(BASE_LIB)
    skill = load(SKILL_LIB)
    base_wf = base['workflows']

    # refresh canonical metadata
    base.setdefault('metadata', {})['total_workflows'] = len(base_wf)

    # figure out the personal source dir from the existing skill library
    personal_src = skill.get('metadata', {}).get('source_dir')

    # backup the current skill library (a local copy of personal workflows is preserved)
    bak = SKILL_LIB + '.bak.' + time.strftime('%Y%m%d_%H%M%S')
    if os.path.exists(SKILL_LIB):
        shutil.copy2(SKILL_LIB, bak)

    if args.no_merge:
        merged = base
        print('no-merge: skill library := canonical base (%d workflows)' % len(base_wf))
    else:
        merged = copy.deepcopy(base)
        added = []
        for k, v in skill.get('workflows', {}).items():
            if k in merged['workflows']:
                continue
            if isinstance(v, dict):
                v = dict(v)
                v['source_root'] = personal_src
            merged['workflows'][k] = v
            added.append(k)
        print('merged personal workflows:', len(added))

    md = merged.setdefault('metadata', {})
    md['canonical_base'] = os.path.relpath(BASE_LIB, REPO_ROOT).replace('\\', '/')
    md['source_roots'] = [os.path.relpath(os.path.dirname(BASE_LIB), REPO_ROOT).replace('\\', '/')]
    if personal_src:
        md['source_roots'].append(personal_src)
    md['total_workflows'] = len(merged['workflows'])
    md['sync_note'] = ('canonical=仓库内 assets 盘点（含 MiniMax + 旧工作流 node_dependencies）；'
                       'personal=本机个人工作流（仅本地，不入 file_index，避免增量更新误删）')
    md['sync_time'] = int(time.time())

    save(BASE_LIB, base)
    save(SKILL_LIB, merged)

    print('canonical (repo) workflows :', len(base_wf))
    print('skill library workflows    :', len(merged['workflows']))
    print('  with node_dependencies   :',
          sum(1 for v in merged['workflows'].values() if isinstance(v, dict) and v.get('node_dependencies')))
    print('  minimax entries          :', [k for k in merged['workflows'] if 'minimax' in k.lower()])
    print('backup ->', os.path.basename(bak))
    print('WROTE', BASE_LIB)
    print('WROTE', SKILL_LIB)


if __name__ == '__main__':
    main()
