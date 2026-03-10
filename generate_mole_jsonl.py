#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from simulator import (
    DEFAULT_MOLE_MODE,
    MOLE_MODE_CONFIG_FIXED,
    MOLE_MODE_CONFIG_FIXED_UNIFORM30,
    MOLE_SPAWN_RATE,
    build_seed_mole_plan,
    load_mole_position_config,
    load_seed_cases,
    resolve_mole_mode,
    SHAPE_BY_ID,
)


def point_index_from_pos(shape, pos):
    if pos is None:
        return None
    r, c = pos
    h = len(shape)
    w = len(shape[0])
    return (h - 1 - r) * w + c


def main():
    ap = argparse.ArgumentParser(description='Generate seed->moles jsonl config.')
    ap.add_argument('--seeds-dir', default='/Users/chase.wang/Documents/New project 13/ExportSeeds')
    ap.add_argument('--out', default='/Users/chase.wang/Documents/New project 13/seed_moles.jsonl')
    ap.add_argument('--mole-mode', default=MOLE_MODE_CONFIG_FIXED_UNIFORM30, choices=[MOLE_MODE_CONFIG_FIXED, MOLE_MODE_CONFIG_FIXED_UNIFORM30, DEFAULT_MOLE_MODE])
    ap.add_argument('--mole-rate', type=float, default=0.30)
    ap.add_argument('--max-seeds', type=int, default=0, help='0 = all')
    args = ap.parse_args()

    seeds_dir = Path(args.seeds_dir)
    out_path = Path(args.out)
    max_seeds = args.max_seeds if args.max_seeds > 0 else 0
    seed_cases = load_seed_cases(seeds_dir, max_seeds)
    pos_map = load_mole_position_config()
    use_guardrails, mole_distribution = resolve_mole_mode(args.mole_mode)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open('w', encoding='utf-8') as f:
        for seed_case in seed_cases:
            plan = build_seed_mole_plan(
                seed_case,
                args.mole_rate,
                use_guardrails,
                mole_distribution,
                {},
            )
            block_ids = seed_case.get('blockIds') or []
            has_mole = plan.get('has_mole') or []
            items = []
            for seq_index, block_id in enumerate(block_ids):
                if seq_index >= len(has_mole) or not has_mole[seq_index]:
                    continue
                shape_id = str(block_id)
                shape = SHAPE_BY_ID.get(shape_id)
                if not shape:
                    continue
                pos = pos_map.get(shape_id)
                idx = point_index_from_pos(shape, pos)
                if idx is None:
                    continue
                items.append(f'{seq_index},{idx}')
            row = {
                'seed': seed_case.get('name', ''),
                'moles': items,
            }
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
            count += 1
    print(f'generated {count} seeds -> {out_path}')


if __name__ == '__main__':
    main()
