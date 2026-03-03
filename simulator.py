#!/usr/bin/env python3
import argparse
import csv
import json
import math
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


GRID_SIZE = 8
TIME_LIMIT = 180.0
MOLE_REWARD_RATE = 0.2
MOLE_SPAWN_RATE = 0.40
FORCE_SECOND_BLOCK = False
FORCE_ONE_MOLE_IN_FIRST_THREE = True
FIXED_RETURN_MULTIPLIER = 2.0
DEFAULT_POLICY = "capture_greedy"
POLICY_META = {
    "capture_greedy": {"version": "V1", "name_zh": "抓鼠贪心"},
    "survival_mobility": {"version": "V2", "name_zh": "生存机动"},
    "lookahead_2ply": {"version": "V3", "name_zh": "双步前瞻"},
    "triplet_beam": {"version": "V4", "name_zh": "三块束搜索"},
}
POLICY_ALIASES = {
    "capture_greedy": "capture_greedy",
    "legacy": "capture_greedy",
    "survival_mobility": "survival_mobility",
    "improved": "survival_mobility",
    "lookahead_2ply": "lookahead_2ply",
    "latest": "lookahead_2ply",
    "triplet_beam": "triplet_beam",
    "beam_triplet": "triplet_beam",
    "抓鼠贪心": "capture_greedy",
    "生存机动": "survival_mobility",
    "双步前瞻": "lookahead_2ply",
    "三块束搜索": "triplet_beam",
    "v1": "capture_greedy",
    "v2": "survival_mobility",
    "v3": "lookahead_2ply",
    "v4": "triplet_beam",
}


BLOCK_FIGURES = [
    {"id": "1111001", "s": [[1]]},
    {"id": "1122003", "s": [[1, 1]]},
    {"id": "1212003", "s": [[1], [1]]},
    {"id": "1222009", "s": [[1, 0], [0, 1]]},
    {"id": "1222006", "s": [[0, 1], [1, 0]]},
    {"id": "1133007", "s": [[1, 1, 1]]},
    {"id": "1313007", "s": [[1], [1], [1]]},
    {"id": "1223007", "s": [[0, 1], [1, 1]]},
    {"id": "1223013", "s": [[1, 1], [0, 1]]},
    {"id": "1223014", "s": [[1, 1], [1, 0]]},
    {"id": "1223011", "s": [[1, 0], [1, 1]]},
    {"id": "1224015", "s": [[1, 1], [1, 1]]},
    {"id": "1234058", "s": [[1, 1, 1], [0, 1, 0]]},
    {"id": "1324046", "s": [[1, 0], [1, 1], [1, 0]]},
    {"id": "1234023", "s": [[0, 1, 0], [1, 1, 1]]},
    {"id": "1324029", "s": [[0, 1], [1, 1], [0, 1]]},
    {"id": "1234015", "s": [[0, 0, 1], [1, 1, 1]]},
    {"id": "1324053", "s": [[1, 1], [0, 1], [0, 1]]},
    {"id": "1234060", "s": [[1, 1, 1], [1, 0, 0]]},
    {"id": "1324043", "s": [[1, 0], [1, 0], [1, 1]]},
    {"id": "1234039", "s": [[1, 0, 0], [1, 1, 1]]},
    {"id": "1324023", "s": [[0, 1], [0, 1], [1, 1]]},
    {"id": "1234057", "s": [[1, 1, 1], [0, 0, 1]]},
    {"id": "1324058", "s": [[1, 1], [1, 0], [1, 0]]},
    {"id": "1234030", "s": [[0, 1, 1], [1, 1, 0]]},
    {"id": "1234051", "s": [[1, 1, 0], [0, 1, 1]]},
    {"id": "1324045", "s": [[1, 0], [1, 1], [0, 1]]},
    {"id": "1324030", "s": [[0, 1], [1, 1], [1, 0]]},
    {"id": "1333273", "s": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    {"id": "1333084", "s": [[0, 0, 1], [0, 1, 0], [1, 0, 0]]},
    {"id": "1144015", "s": [[1, 1, 1, 1]]},
    {"id": "1414015", "s": [[1], [1], [1], [1]]},
    {"id": "1326063", "s": [[1, 1], [1, 1], [1, 1]]},
    {"id": "1236063", "s": [[1, 1, 1], [1, 1, 1]]},
    {"id": "1155031", "s": [[1, 1, 1, 1, 1]]},
    {"id": "1515031", "s": [[1], [1], [1], [1], [1]]},
    {"id": "1335079", "s": [[0, 0, 1], [0, 0, 1], [1, 1, 1]]},
    {"id": "1335457", "s": [[1, 1, 1], [0, 0, 1], [0, 0, 1]]},
    {"id": "1335484", "s": [[1, 1, 1], [1, 0, 0], [1, 0, 0]]},
    {"id": "1335295", "s": [[1, 0, 0], [1, 0, 0], [1, 1, 1]]},
    {"id": "1339511", "s": [[1, 1, 1], [1, 1, 1], [1, 1, 1]]},
]
SHAPE_BY_ID = {x["id"]: x["s"] for x in BLOCK_FIGURES}

MOLE_WHITELIST = {
    "1224015", "1133007", "1313007", "1223007", "1223013", "1223014", "1223011",
    "1234058", "1234023", "1324046", "1324029", "1234060", "1234039", "1234015",
    "1234057", "1324043", "1324023", "1324053", "1324058",
}
MOLE_BLACKLIST = {
    "1333273", "1333084", "1335079", "1335457", "1335484", "1335295", "1339511",
    "1144015", "1414015", "1222009", "1222006",
}


@dataclass
class Mole:
    r: int
    c: int
    block_id: int
    freeze_turns: int = 1


@dataclass
class Piece:
    shape_id: str
    shape: List[List[int]]
    seq_index: int
    has_mole: bool
    mole_pos: Optional[Tuple[int, int]]


def parse_difficulty(seed_name: str) -> str:
    m = re.search(r"_(D(E|\d+)|R\d+)_", seed_name, re.I)
    if not m:
        return "Unknown"
    token = m.group(1).upper()
    return "Easy" if token == "DE" else token


def normalize_policy(policy: str) -> str:
    key = (policy or "").strip().lower()
    return POLICY_ALIASES.get(key, DEFAULT_POLICY)


def policy_display_name(policy: str) -> str:
    p = normalize_policy(policy)
    meta = POLICY_META.get(p, POLICY_META[DEFAULT_POLICY])
    return f"{meta['version']}-{meta['name_zh']}"


def build_seed_pool(seed_cases: List[dict], difficulty: str = "D5", prefer_unique_initial: bool = True) -> List[dict]:
    diff = (difficulty or "ALL").strip().upper()
    if diff in ("ALL", "*"):
        filtered = list(seed_cases)
    elif diff in ("EASY", "DE"):
        filtered = [s for s in seed_cases if parse_difficulty(s.get("name", "")) == "Easy"]
    else:
        filtered = [s for s in seed_cases if parse_difficulty(s.get("name", "")) == diff]

    if not prefer_unique_initial:
        return filtered

    unique = []
    dup = []
    seen = set()
    for s in filtered:
        key = tuple(s.get("initialGrid", []))
        if key in seen:
            dup.append(s)
        else:
            seen.add(key)
            unique.append(s)
    # "Prefer unique" (not strict): unique first, then duplicates.
    return unique + dup


def build_run_seed_list(seed_cases: List[dict], runs: int, rng: random.Random) -> List[dict]:
    if runs <= 0 or not seed_cases:
        return []
    # Minimize duplicates: sample without replacement per cycle, reshuffle next cycle.
    out = []
    n = len(seed_cases)
    while len(out) < runs:
        bucket = list(seed_cases)
        rng.shuffle(bucket)
        take = min(runs - len(out), n)
        out.extend(bucket[:take])
    return out


def deterministic_roll01(seq_index: int, salt: int = 0) -> float:
    x = (seq_index + 1) ^ salt
    x = ((x ^ (x >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    x = ((x ^ (x >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    x = x ^ (x >> 16)
    return (x & 0xFFFFFFFF) / 4294967296.0


def get_mole_pattern_salt(multiplier: float) -> int:
    if multiplier == 2:
        return 0x2F6E2B1
    if multiplier == 2.5:
        return 0x5A31C9D
    if multiplier == 3:
        return 0x7CB4A11
    return 0x1F123BB


def count_active_cells(shape: List[List[int]]) -> int:
    return sum(v for row in shape for v in row)


def is_mole_eligible(shape_id: str) -> bool:
    return shape_id in MOLE_WHITELIST and shape_id not in MOLE_BLACKLIST


def can_place(grid: List[List[int]], shape: List[List[int]], r: int, c: int) -> bool:
    for i, row in enumerate(shape):
        for j, v in enumerate(row):
            if not v:
                continue
            nr, nc = r + i, c + j
            if nr < 0 or nc < 0 or nr >= GRID_SIZE or nc >= GRID_SIZE or grid[nr][nc]:
                return False
    return True


def full_rows_cols(grid: List[List[int]]) -> Tuple[List[int], List[int]]:
    rows = [i for i in range(GRID_SIZE) if all(grid[i][c] == 1 for c in range(GRID_SIZE))]
    cols = [i for i in range(GRID_SIZE) if all(grid[r][i] == 1 for r in range(GRID_SIZE))]
    return rows, cols


def simulate(
    seed_case: dict,
    rng: random.Random,
    entry_fee: float,
    action_seconds: float,
    max_actions: int,
    goal_target: int = 6,
    max_moles_cap: int = 10,
    mole_spawn_rate: float = 0.30,
    policy: str = "legacy",
    collect_trace: bool = False,
    mole_reward_rate: float = MOLE_REWARD_RATE,
) -> dict:
    grid = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]
    holes = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]
    hole_visits = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]
    hole_block = [[-1] * GRID_SIZE for _ in range(GRID_SIZE)]
    moles: List[Mole] = []
    time_left = TIME_LIMIT
    seq_cursor = 0
    result = "Fail"
    block_entity_id = 0
    placed = 0
    clear_events = 0
    captured = 0
    spawned = 0
    max_alive_moles = 0
    max_no_mole_place_streak = 0
    current_no_mole_place_streak = 0
    rows_cleared = 0
    cols_cleared = 0
    cells_cleared = 0

    initial = seed_case["initialGrid"]
    for r in range(GRID_SIZE):
        bits = initial[r] if r < len(initial) else 0
        for c in range(GRID_SIZE):
            grid[r][c] = 1 if ((bits >> (GRID_SIZE - 1 - c)) & 1) else 0

    block_ids = seed_case["blockIds"]
    if not block_ids:
        raise ValueError(f"seed has empty sequence: {seed_case['name']}")

    multiplier = FIXED_RETURN_MULTIPLIER
    max_moles_cap = max(1, int(max_moles_cap))
    mole_spawn_rate = min(1.0, max(0.0, float(mole_spawn_rate)))
    mole_reward_rate = max(0.0, float(mole_reward_rate))
    mole_reward = entry_fee * mole_reward_rate
    max_reward = max_moles_cap * mole_reward
    salt = get_mole_pattern_salt(multiplier) ^ (1 * 131)
    pos_salt = (get_mole_pattern_salt(multiplier) >> 6) + 17

    def next_piece_triplet() -> List[Piece]:
        nonlocal seq_cursor
        pieces = []
        for _ in range(3):
            idx = seq_cursor % len(block_ids)
            seq = seq_cursor
            sid = block_ids[idx]
            shape = SHAPE_BY_ID[sid]
            pieces.append(Piece(shape_id=sid, shape=shape, seq_index=seq, has_mole=False, mole_pos=None))
            seq_cursor += 1

        eligible_idx = [i for i, p in enumerate(pieces) if is_mole_eligible(p.shape_id)]

        if FORCE_SECOND_BLOCK and len(pieces) > 1 and is_mole_eligible(pieces[1].shape_id):
            pieces[1].has_mole = True

        if FORCE_ONE_MOLE_IN_FIRST_THREE:
            has = any(p.seq_index < 3 and p.has_mole for p in pieces)
            if not has:
                first_three = [i for i, p in enumerate(pieces) if p.seq_index < 3]
                first_eligible = [i for i, p in enumerate(pieces) if p.seq_index < 3 and is_mole_eligible(p.shape_id)]
                if len(first_eligible) == len(first_three) and first_eligible:
                    pick = max(first_eligible, key=lambda i: (count_active_cells(pieces[i].shape), -i))
                    pieces[pick].has_mole = True
                elif first_eligible:
                    pick = 1 if 1 in first_eligible else first_eligible[0]
                    pieces[pick].has_mole = True
                elif first_three:
                    pick = min(first_three, key=lambda i: (count_active_cells(pieces[i].shape), i))
                    pieces[pick].has_mole = True

        for i in eligible_idx:
            if pieces[i].has_mole:
                continue
            if deterministic_roll01(pieces[i].seq_index, salt) < mole_spawn_rate:
                pieces[i].has_mole = True

        for p in pieces:
            valid = [(r, c) for r, row in enumerate(p.shape) for c, v in enumerate(row) if v]
            if p.has_mole and (is_mole_eligible(p.shape_id) or p.seq_index < 3):
                j = (p.seq_index + pos_salt) % len(valid)
                p.mole_pos = valid[j]
            else:
                p.has_mole = False
                p.mole_pos = None
        return pieces

    def apply_piece(p: Piece, rr: int, cc: int):
        nonlocal block_entity_id, spawned, placed, max_alive_moles, max_no_mole_place_streak, current_no_mole_place_streak
        placed += 1
        if p.has_mole:
            current_no_mole_place_streak = 0
        else:
            current_no_mole_place_streak += 1
            max_no_mole_place_streak = max(max_no_mole_place_streak, current_no_mole_place_streak)
        local_block_id = block_entity_id
        block_entity_id += 1
        for i, row in enumerate(p.shape):
            for j, v in enumerate(row):
                if not v:
                    continue
                r, c = rr + i, cc + j
                grid[r][c] = 1
                if p.has_mole:
                    holes[r][c] = 1
                    hole_block[r][c] = local_block_id
                    hole_visits[r][c] = 0
        if p.has_mole and p.mole_pos is not None:
            mr, mc = p.mole_pos
            moles.append(Mole(rr + mr, cc + mc, local_block_id, 1))
            spawned += 1
            max_alive_moles = max(max_alive_moles, len(moles))

    def clear_and_capture():
        nonlocal clear_events, captured, rows_cleared, cols_cleared, cells_cleared
        rows, cols = full_rows_cols(grid)
        if not rows and not cols:
            return {"did_clear": False, "rows": [], "cols": [], "captured": 0}
        clear_events += 1
        rows_cleared += len(rows)
        cols_cleared += len(cols)
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if r in rows or c in cols:
                    cells_cleared += 1
        captured_this = 0
        keep = []
        for m in moles:
            if m.r in rows or m.c in cols:
                captured += 1
                captured_this += 1
            else:
                keep.append(m)
        moles[:] = keep
        for r in rows:
            for c in range(GRID_SIZE):
                grid[r][c] = 0
                holes[r][c] = 0
                hole_visits[r][c] = 0
                hole_block[r][c] = -1
        for c in cols:
            for r in range(GRID_SIZE):
                grid[r][c] = 0
                holes[r][c] = 0
                hole_visits[r][c] = 0
                hole_block[r][c] = -1
        return {"did_clear": True, "rows": rows, "cols": cols, "captured": captured_this}

    def move_moles():
        for m in moles:
            if m.freeze_turns > 0:
                m.freeze_turns -= 1
                continue
            candidates = []
            for order, (dr, dc) in enumerate([(0, 1), (1, 0), (0, -1), (-1, 0)]):
                nr, nc = m.r + dr, m.c + dc
                if nr < 0 or nc < 0 or nr >= GRID_SIZE or nc >= GRID_SIZE:
                    continue
                if not holes[nr][nc]:
                    continue
                if hole_block[nr][nc] != m.block_id:
                    continue
                candidates.append((hole_visits[nr][nc], order, nr, nc))
            if candidates:
                _, _, nr, nc = min(candidates)
                m.r, m.c = nr, nc
                hole_visits[nr][nc] += 1

        reachable = [[False] * GRID_SIZE for _ in range(GRID_SIZE)]
        q = [(m.r, m.c, m.block_id) for m in moles]
        for r, c, _ in q:
            reachable[r][c] = True
        qi = 0
        while qi < len(q):
            r, c, bid = q[qi]
            qi += 1
            for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nr, nc = r + dr, c + dc
                if nr < 0 or nc < 0 or nr >= GRID_SIZE or nc >= GRID_SIZE:
                    continue
                if reachable[nr][nc] or not holes[nr][nc] or hole_block[nr][nc] != bid:
                    continue
                reachable[nr][nc] = True
                q.append((nr, nc, bid))

        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if holes[r][c] and not reachable[r][c]:
                    holes[r][c] = 0
                    hole_visits[r][c] = 0
                    hole_block[r][c] = -1

    def predict(piece: Piece, rr: int, cc: int) -> Tuple[int, int, int]:
        temp = [row[:] for row in grid]
        for i, row in enumerate(piece.shape):
            for j, v in enumerate(row):
                if v:
                    temp[rr + i][cc + j] = 1
        rows, cols = full_rows_cols(temp)
        clear_cells = 0
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if r in rows or c in cols:
                    clear_cells += 1
        cap = sum(1 for m in moles if m.r in rows or m.c in cols)
        return cap, clear_cells, len(rows) + len(cols)

    def apply_shape_and_clear(base_grid: List[List[int]], shape: List[List[int]], rr: int, cc: int):
        temp = [row[:] for row in base_grid]
        for i, row in enumerate(shape):
            for j, v in enumerate(row):
                if v:
                    temp[rr + i][cc + j] = 1
        rows, cols = full_rows_cols(temp)
        clear_cells = 0
        if rows or cols:
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    if r in rows or c in cols:
                        clear_cells += 1
            for r in rows:
                for c in range(GRID_SIZE):
                    temp[r][c] = 0
            for c in cols:
                for r in range(GRID_SIZE):
                    temp[r][c] = 0
        return temp, rows, cols, clear_cells

    def count_piece_placements(base_grid: List[List[int]], piece: Piece) -> int:
        cnt = 0
        for rr in range(GRID_SIZE):
            for cc in range(GRID_SIZE):
                if can_place(base_grid, piece.shape, rr, cc):
                    cnt += 1
        return cnt

    def base_move_score(base_grid: List[List[int]], pieces: List[Piece], pick_idx: int, rr: int, cc: int, cap_override: Optional[int] = None):
        p = pieces[pick_idx]
        fill = count_active_cells(p.shape)
        temp, rows, cols, clear_cells = apply_shape_and_clear(base_grid, p.shape, rr, cc)
        lines = len(rows) + len(cols)
        cap = cap_override if cap_override is not None else sum(1 for m in moles if m.r in rows or m.c in cols)
        free_after = sum(1 for r in range(GRID_SIZE) for c in range(GRID_SIZE) if temp[r][c] == 0)
        remain = [pp for i2, pp in enumerate(pieces) if i2 != pick_idx and pp is not None]
        mobility = sum(count_piece_placements(temp, rp) for rp in remain)
        min_fit = min((count_piece_placements(temp, rp) for rp in remain), default=12)
        return {
            "grid_after": temp,
            "rows": rows,
            "cols": cols,
            "cap": cap,
            "lines": lines,
            "clear_cells": clear_cells,
            "fill": fill,
            "free_after": free_after,
            "mobility": mobility,
            "min_fit": min_fit,
        }

    def score_survival(detail: dict) -> float:
        return (
            (detail["cap"] * 1800)
            + (detail["lines"] * 180)
            + (detail["clear_cells"] * 3)
            + (detail["mobility"] * 2)
            + detail["free_after"]
            + (detail["min_fit"] * 4)
            - (detail["fill"] * 2)
        )

    def score_adaptive(detail: dict) -> float:
        goal_progress = 0.0 if goal_target <= 0 else min(1.0, captured / max(1, goal_target))
        cap_w = 1700 + (700 * goal_progress)
        line_w = 160 + (80 * goal_progress)
        mobility_w = 3.2 - (1.4 * goal_progress)
        min_fit_w = 24.0 - (8.0 * goal_progress)
        return (
            (detail["cap"] * cap_w)
            + (detail["lines"] * line_w)
            + (detail["clear_cells"] * 3.3)
            + (detail["mobility"] * mobility_w)
            + (detail["min_fit"] * min_fit_w)
            + (detail["free_after"] * 1.1)
            - (detail["fill"] * 2.5)
        )

    def top_piece_moves(base_grid: List[List[int]], pieces_local: List[Piece], pick_idx: int, cap_override: int, limit: int, use_adaptive: bool):
        out = []
        piece = pieces_local[pick_idx]
        for rr in range(GRID_SIZE):
            for cc in range(GRID_SIZE):
                if not can_place(base_grid, piece.shape, rr, cc):
                    continue
                d = base_move_score(base_grid, pieces_local, pick_idx, rr, cc, cap_override=cap_override)
                sc = score_adaptive(d) if use_adaptive else score_survival(d)
                out.append((sc, rr, cc, d))
        out.sort(key=lambda x: x[0], reverse=True)
        return out[:limit]

    def best_second_step(first_detail: dict, remain_pieces: List[Piece], alive_after_first: List[Mole]) -> float:
        second_best = -1e9
        for j, p2 in enumerate(remain_pieces):
            if p2 is None:
                continue
            for r2 in range(GRID_SIZE):
                for c2 in range(GRID_SIZE):
                    if not can_place(first_detail["grid_after"], p2.shape, r2, c2):
                        continue
                    after2, rows2, cols2, clear2 = apply_shape_and_clear(first_detail["grid_after"], p2.shape, r2, c2)
                    cap2 = sum(1 for mol in alive_after_first if mol.r in rows2 or mol.c in cols2)
                    rem2 = [pp if idx != j else None for idx, pp in enumerate(remain_pieces)]
                    rem2 = [x for x in rem2 if x is not None]
                    mobility2 = 0
                    min_fit2 = 12
                    for rp in rem2:
                        cnt = count_piece_placements(after2, rp)
                        mobility2 += cnt
                        min_fit2 = min(min_fit2, cnt)
                    free2 = sum(1 for r3 in range(GRID_SIZE) for c3 in range(GRID_SIZE) if after2[r3][c3] == 0)
                    second_score = (
                        cap2 * 1400
                        + (len(rows2) + len(cols2)) * 160
                        + clear2 * 2
                        + mobility2 * 2
                        + min_fit2 * 8
                        + free2
                    )
                    if second_score > second_best:
                        second_best = second_score
        return second_best

    def best_triplet_continuation(first_detail: dict, remain_pieces: List[Piece]) -> float:
        pieces_left = [p for p in remain_pieces if p is not None]
        if not pieces_left:
            return 0.0

        best = -1e9
        for first_idx in range(len(pieces_left)):
            first_moves = top_piece_moves(
                first_detail["grid_after"],
                pieces_left,
                first_idx,
                cap_override=0,
                limit=9,
                use_adaptive=True,
            )
            if not first_moves:
                continue
            for sc_a, _, _, d_a in first_moves:
                remaining_after_a = [p for idx, p in enumerate(pieces_left) if idx != first_idx]
                if not remaining_after_a:
                    best = max(best, sc_a)
                    continue
                second_moves = top_piece_moves(
                    d_a["grid_after"],
                    remaining_after_a,
                    0,
                    cap_override=0,
                    limit=9,
                    use_adaptive=True,
                )
                if not second_moves:
                    total = sc_a - 2200
                else:
                    total = sc_a + 0.88 * second_moves[0][0]
                best = max(best, total)
        return best

    def all_moves(pieces: List[Piece], policy_mode: str = DEFAULT_POLICY):
        mode = normalize_policy(policy_mode)
        moves = []

        for i, p in enumerate(pieces):
            if p is None:
                continue
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    if not can_place(grid, p.shape, r, c):
                        continue
                    cap, cells, lines = predict(p, r, c)
                    fill = count_active_cells(p.shape)
                    detail = base_move_score(grid, pieces, i, r, c, cap_override=cap)

                    if mode == "capture_greedy":
                        score = (cap * 1000) + (lines * 100) + (cells * 2) - fill
                    elif mode == "survival_mobility":
                        score = score_survival(detail)
                    else:
                        score = score_survival(detail)
                    moves.append({"score": score, "tie": rng.random(), "i": i, "r": r, "c": c, "detail": detail})

        if mode in {"capture_greedy", "survival_mobility"} or not moves:
            return [(m["score"], m["tie"], m["i"], m["r"], m["c"]) for m in moves]

        moves.sort(key=lambda m: (m["score"], m["tie"]), reverse=True)
        top = moves[: min(30, len(moves))]

        for m in top:
            i, rr, cc = m["i"], m["r"], m["c"]
            first = m["detail"] or base_move_score(grid, pieces, i, rr, cc)
            remain_pieces = [pp if idx != i else None for idx, pp in enumerate(pieces)]
            alive_after_first = [mol for mol in moles if not (mol.r in first["rows"] or mol.c in first["cols"])]

            if mode == "lookahead_2ply":
                second_best = best_second_step(first, remain_pieces, alive_after_first)
                if second_best < -1e8:
                    second_best = first["free_after"] + first["mobility"]
                m["score"] = m["score"] + (0.62 * second_best) + (first["min_fit"] * 18)
            else:  # triplet_beam: newest
                second_best = best_second_step(first, remain_pieces, alive_after_first)
                if second_best < -1e8:
                    second_best = first["free_after"] + first["mobility"]
                third_best = best_triplet_continuation(first, remain_pieces)
                if third_best < -1e8:
                    third_best = second_best
                m["score"] = (
                    score_adaptive(first)
                    + (0.58 * second_best)
                    + (0.44 * third_best)
                    + (first["min_fit"] * 20)
                )

        return [(m["score"], m["tie"], m["i"], m["r"], m["c"]) for m in moves]

    pieces = next_piece_triplet()
    actions = 0
    trace = []

    def snapshot_board() -> List[str]:
        chars = [["." for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if grid[r][c]:
                    chars[r][c] = "#"
                if holes[r][c]:
                    chars[r][c] = "o"
        for m in moles:
            chars[m.r][m.c] = "M"
        return ["".join(row) for row in chars]

    policy_mode = normalize_policy(policy)
    while actions < max_actions:
        moves = all_moves(pieces, policy_mode)
        if not moves:
            break
        score, tie, i, r, c = max(moves)
        chosen = pieces[i]
        pred_cap, pred_cells, pred_lines = predict(chosen, r, c)
        apply_piece(chosen, r, c)
        pieces[i] = None
        if all(p is None for p in pieces):
            pieces = next_piece_triplet()

        clear_info = clear_and_capture()
        move_moles()
        max_alive_moles = max(max_alive_moles, len(moles))
        actions += 1
        time_left -= action_seconds
        trace.append(
            {
                "turn": actions,
                "piece": chosen.shape_id,
                "place": [r, c],
                "score": score,
                "predictedCapture": pred_cap,
                "predictedLines": pred_lines,
                "predictedClearedCells": pred_cells,
                "clearedRows": clear_info["rows"],
                "clearedCols": clear_info["cols"],
                "capturedThisTurn": clear_info["captured"],
                "capturedTotal": captured,
                "molesAlive": len(moles),
                "timeLeft": max(0.0, time_left),
                "board": snapshot_board(),
            }
        )
        earned = min(captured * mole_reward, max_reward)
        if earned >= max_reward:
            result = "MaxWin"
            break
        if time_left <= 0:
            result = "GoalWin" if captured >= goal_target else "Fail"
            break
        if not all_moves(pieces, policy_mode):
            result = "GoalWin" if captured >= goal_target else "Fail"
            break
    else:
        earned = min(captured * mole_reward, max_reward)
        result = "GoalWin" if captured >= goal_target else "Fail"

    earned = min(captured * mole_reward, max_reward)
    if earned >= max_reward:
        result = "MaxWin"

    out = {
        "seed": seed_case["name"],
        "difficulty": parse_difficulty(seed_case["name"]),
        "result": result,
        "stake": entry_fee,
        "earned": 0.0 if result == "Fail" else earned,
        "rtp": (0.0 if result == "Fail" else earned) / entry_fee,
        "blocksPlaced": placed,
        "clearEvents": clear_events,
        "rowsCleared": rows_cleared,
        "colsCleared": cols_cleared,
        "clearedCells": cells_cleared,
        "molesSpawned": spawned,
        "molesCaptured": captured,
        "maxAliveMoles": max_alive_moles,
        "maxNoMolePlaceStreak": max(max_no_mole_place_streak, current_no_mole_place_streak),
        "remainingTime": -1 if math.isinf(time_left) else max(0.0, time_left),
        "policy": policy_display_name(policy_mode),
        "policyKey": policy_mode,
        "goalTarget": goal_target,
        "maxMolesCap": max_moles_cap,
        "moleSpawnRate": mole_spawn_rate,
        "moleRewardRate": mole_reward_rate,
        "rewardPerMoleDollar": mole_reward,
        "maxReward": max_reward,
    }
    if collect_trace:
        out["trace"] = trace
    return out


def load_seed_cases(seeds_dir: Path, max_seeds: int = 0) -> List[dict]:
    if seeds_dir.name != "ExportSeeds" and (seeds_dir / "ExportSeeds").is_dir():
        seeds_dir = seeds_dir / "ExportSeeds"

    def stable_name_hash(name: str) -> int:
        # Deterministic lightweight hash; used to avoid lexicographic sampling bias.
        x = 2166136261
        for ch in name:
            x ^= ord(ch)
            x = (x * 16777619) & 0xFFFFFFFF
        return x

    out = []
    files = sorted(seeds_dir.glob("*.jsonl"))
    if max_seeds and max_seeds > 0 and len(files) > max_seeds:
        # Deterministically "shuffle" by filename hash before truncation so sampled seeds
        # are not concentrated in contiguous board ranges.
        files = sorted(files, key=lambda p: stable_name_hash(p.name))[:max_seeds]
    for p in files:
        with p.open("r", encoding="utf-8") as f:
            line = f.readline().strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(
                {
                    "file": p.name,
                    "name": d.get("case_hash", p.stem),
                    "initialGrid": d.get("initial_grid", [0] * GRID_SIZE),
                    "blockIds": [x.get("block_id") for x in d.get("block_sequence", []) if x.get("block_id")],
                }
            )
    return out


def summarize(rows: List[dict]):
    if not rows:
        print("No rows.")
        return
    total_stake = sum(r["stake"] for r in rows)
    total_earned = sum(r["earned"] for r in rows)
    win = sum(1 for r in rows if r["result"] != "Fail")
    print(f"matches: {len(rows)}")
    print(f"win-rate: {win/len(rows):.3f}")
    print(f"RTP: {total_earned/total_stake:.3f}  (earned={total_earned:.2f}, stake={total_stake:.2f})")

    by_diff: Dict[str, List[dict]] = {}
    for r in rows:
        by_diff.setdefault(r["difficulty"], []).append(r)
    print("\nby difficulty:")
    for diff in sorted(by_diff.keys()):
        rs = by_diff[diff]
        st = sum(x["stake"] for x in rs)
        ea = sum(x["earned"] for x in rs)
        wr = sum(1 for x in rs if x["result"] != "Fail") / len(rs)
        print(f"{diff:>7}  n={len(rs):5d}  win={wr:.3f}  RTP={ea/st:.3f}")


def main():
    ap = argparse.ArgumentParser(description="Block+Mole simulator over ExportSeeds.")
    ap.add_argument("--seeds-dir", default="/Users/chase.wang/ugx_block_seed/Data/ExportSeeds", help="Directory containing *.jsonl seeds")
    ap.add_argument("--runs", type=int, default=100, help="Number of simulated matches (0 = one per seed)")
    ap.add_argument("--entry-fee", type=float, default=1.0)
    ap.add_argument("--goal-target", type=int, default=6, help="Required mole captures to count as clear")
    ap.add_argument("--max-moles", type=int, default=10, help="Mole capture cap for max reward")
    ap.add_argument("--mole-rate", type=float, default=0.40, help="Mole coverage rate [0,1]")
    ap.add_argument("--mole-reward-rate", type=float, default=MOLE_REWARD_RATE, help="Single-mole reward coefficient vs entry fee")
    ap.add_argument("--difficulty", default="D5", help="Difficulty filter, e.g. D5/Easy/R14/ALL")
    ap.add_argument(
        "--prefer-unique-initial",
        dest="prefer_unique_initial",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prefer different initial boards first",
    )
    ap.add_argument(
        "--policy",
        default=DEFAULT_POLICY,
        help="策略: V1-抓鼠贪心 / V2-生存机动 / V3-双步前瞻 / V4-三块束搜索（仍支持 legacy/improved/latest）",
    )
    ap.add_argument("--action-seconds", type=float, default=2.0, help="Seconds consumed per placement")
    ap.add_argument("--max-actions", type=int, default=150)
    ap.add_argument("--rng-seed", type=int, default=20260302)
    ap.add_argument("--max-seeds", type=int, default=10000, help="Load first N seed files (0 = all)")
    ap.add_argument("--out-csv", default="", help="Optional output CSV path")
    args = ap.parse_args()
    policy = normalize_policy(args.policy)

    t0 = time.perf_counter()
    seeds_dir = Path(args.seeds_dir)
    seed_cases = load_seed_cases(seeds_dir, args.max_seeds)
    seed_cases = build_seed_pool(seed_cases, args.difficulty, args.prefer_unique_initial)
    if not seed_cases:
        raise SystemExit(f"No seeds after filtering. dir={seeds_dir}, difficulty={args.difficulty}")

    rng = random.Random(args.rng_seed)
    rows = []

    if args.runs and args.runs > 0:
        for sc in build_run_seed_list(seed_cases, args.runs, rng):
            rows.append(
                simulate(
                    sc,
                    rng,
                    args.entry_fee,
                    args.action_seconds,
                    args.max_actions,
                    args.goal_target,
                    args.max_moles,
                    args.mole_rate,
                    policy,
                    False,
                    args.mole_reward_rate,
                )
            )
    else:
        for sc in seed_cases:
            rows.append(
                simulate(
                    sc,
                    rng,
                    args.entry_fee,
                    args.action_seconds,
                    args.max_actions,
                    args.goal_target,
                    args.max_moles,
                    args.mole_rate,
                    policy,
                    False,
                    args.mole_reward_rate,
                )
            )

    elapsed = time.perf_counter() - t0
    summarize(rows)
    print(f"duration: {elapsed:.3f}s")

    if args.out_csv:
        fieldnames = list(rows[0].keys())
        with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"\nSaved: {args.out_csv}")


if __name__ == "__main__":
    main()
