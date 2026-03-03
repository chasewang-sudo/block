#!/usr/bin/env python3
import argparse
import html
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from simulator import (
    DEFAULT_POLICY,
    MOLE_REWARD_RATE,
    build_run_seed_list,
    build_seed_pool,
    load_seed_cases,
    normalize_policy,
    policy_display_name,
    simulate,
)


LAST_CSV = b""
LAST_CSV_NAME = "sim_results.csv"

FIELD_LABELS_ZH = {
    "seed": "种子名",
    "difficulty": "难度",
    "level": "关卡",
    "mode": "模式",
    "stake": "下注金额",
    "returnMultiplier": "返奖倍率",
    "goalTarget": "过关目标(地鼠数)",
    "maxMolesCap": "最大奖励上限(地鼠数)",
    "moleSpawnRate": "鼹鼠覆盖率(0~1)",
    "moleCoverage": "鼹鼠覆盖率(0~1)",
    "moleRewardRate": "单鼠奖励系数",
    "rewardPerMoleDollar": "单鼠奖励金额($)",
    "maxReward": "最大奖励金额($)",
    "maxRewardDollar": "最大奖励金额($)",
    "totalBlocksInSeed": "种子总块数",
    "blocksPlaced": "放置块数",
    "clearEvents": "消除次数",
    "rowsCleared": "消除行数",
    "colsCleared": "消除列数",
    "clearedCells": "消除格子数",
    "molesSpawned": "生成鼹鼠数",
    "molesCaptured": "捕获鼹鼠数",
    "maxAliveMoles": "场上同时未消除鼹鼠峰值",
    "maxNoMolePlaceStreak": "连续未放置带鼠块次数峰值",
    "earned": "本局收益",
    "goalReached": "是否达成Goal",
    "maxRewardReached": "是否达到最大奖励",
    "remainingTime": "剩余时间(秒/∞=-1)",
    "result": "比赛结果",
    "policy": "策略版本",
    "policyKey": "策略键",
    "rtp": "返奖率",
}

PREFERRED_FIELD_ORDER = [
    "startedAt",
    "endedAt",
    "seed",
    "difficulty",
    "level",
    "mode",
    "stake",
    "returnMultiplier",
    "goalTarget",
    "maxMolesCap",
    "moleCoverage",
    "moleSpawnRate",
    "moleRewardRate",
    "rewardPerMoleDollar",
    "maxRewardDollar",
    "maxReward",
    "totalBlocksInSeed",
    "blocksPlaced",
    "clearEvents",
    "rowsCleared",
    "colsCleared",
    "clearedCells",
    "molesSpawned",
    "molesCaptured",
    "maxAliveMoles",
    "maxNoMolePlaceStreak",
    "earned",
    "goalReached",
    "maxRewardReached",
    "remainingTime",
    "result",
    "policy",
    "policyKey",
    "rtp",
]


def to_int(val: str, default: int) -> int:
    try:
        return int(val)
    except Exception:
        return default


def to_float(val: str, default: float) -> float:
    try:
        return float(val)
    except Exception:
        return default


def ordered_fields(rows):
    if not rows:
        return []
    keys = list(rows[0].keys())
    ordered = [k for k in PREFERRED_FIELD_ORDER if k in keys]
    ordered.extend([k for k in keys if k not in ordered])
    return ordered


def build_csv(rows):
    if not rows:
        return b""
    header = ordered_fields(rows)
    zh = [FIELD_LABELS_ZH.get(k, k) for k in header]
    lines = [",".join(header), ",".join(zh)]
    for row in rows:
        parts = []
        for k in header:
            v = str(row.get(k, ""))
            if "," in v or '"' in v:
                v = '"' + v.replace('"', '""') + '"'
            parts.append(v)
        lines.append(",".join(parts))
    return ("\n".join(lines) + "\n").encode("utf-8")


def summarize(rows, duration_seconds: float = 0.0):
    if not rows:
        return {"matches": 0, "win_rate": 0.0, "rtp": 0.0, "stake": 0.0, "earned": 0.0, "duration_seconds": duration_seconds}
    stake = sum(r["stake"] for r in rows)
    earned = sum(r["earned"] for r in rows)
    win = sum(1 for r in rows if r["result"] != "Fail")
    return {
        "matches": len(rows),
        "win_rate": win / len(rows),
        "rtp": (earned / stake) if stake > 0 else 0.0,
        "stake": stake,
        "earned": earned,
        "duration_seconds": duration_seconds,
    }


def render_page(defaults, summary=None, rows=None, error=""):
    rows = rows or []
    diff_val = str(defaults.get("difficulty", "D5")).upper()
    policy_val = normalize_policy(str(defaults.get("policy", DEFAULT_POLICY)))
    diff_options = ["D5", "Easy", "D0", "D1", "D2", "D3", "D4", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "R13", "R14", "ALL"]
    diff_select = "".join(
        f'<option value="{d}" {"selected" if diff_val == d.upper() else ""}>{d}</option>' for d in diff_options
    )
    policy_options = [
        ("capture_greedy", policy_display_name("capture_greedy")),
        ("survival_mobility", policy_display_name("survival_mobility")),
        ("lookahead_2ply", policy_display_name("lookahead_2ply")),
        ("triplet_beam", policy_display_name("triplet_beam")),
    ]
    policy_select = "".join(
        f'<option value="{v}" {"selected" if policy_val == v else ""}>{label}</option>' for v, label in policy_options
    )
    summary_html = ""
    if summary:
        summary_html = f"""
        <div class="card">
          <h3>结果总览</h3>
          <div class="stats">
            <div>对局数: <b>{summary['matches']}</b></div>
            <div>胜率: <b>{summary['win_rate']:.2%}</b></div>
            <div>RTP: <b>{summary['rtp']:.3f}</b></div>
            <div>总下注: <b>${summary['stake']:.2f}</b></div>
            <div>总返奖: <b>${summary['earned']:.2f}</b></div>
            <div>模拟耗时: <b>{summary.get('duration_seconds', 0.0):.3f}s</b></div>
          </div>
          <a class="btn" href="/download">下载CSV</a>
        </div>
        """

    table_html = ""
    if rows:
        header_fields = ordered_fields(rows)
        head = "".join(
            f"<th>{html.escape(k)}<br><small>{html.escape(FIELD_LABELS_ZH.get(k, ''))}</small></th>"
            for k in header_fields
        )
        body = []
        for row in rows[:300]:
            tds = "".join(f"<td>{html.escape(str(row.get(k, '')))}</td>" for k in header_fields)
            body.append(f"<tr>{tds}</tr>")
        table_html = f"""
        <div class="card">
          <h3>明细（最多显示300行）</h3>
          <div class="table-wrap">
            <table>
              <thead><tr>{head}</tr></thead>
              <tbody>{''.join(body)}</tbody>
            </table>
          </div>
        </div>
        """

    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Simulator UI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f5f6f8; color: #111; }}
    .wrap {{ max-width: 1080px; margin: 24px auto; padding: 0 16px 32px; }}
    .card {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 4px 18px rgba(0,0,0,.06); margin-bottom: 14px; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    label {{ font-size: 12px; color: #666; display: block; margin-bottom: 4px; }}
    input, select {{ width: 100%; box-sizing: border-box; height: 36px; border: 1px solid #d7dbe2; border-radius: 8px; padding: 0 10px; }}
    .btn {{ display: inline-flex; align-items: center; justify-content: center; height: 38px; border-radius: 8px; background: #0d6efd; color: #fff; border: 0; padding: 0 14px; text-decoration: none; cursor: pointer; }}
    .actions {{ margin-top: 12px; display: flex; gap: 10px; }}
    .stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 10px; }}
    .err {{ background: #ffe7e7; color: #b00020; border-radius: 10px; padding: 10px 12px; margin: 10px 0; }}
    table {{ border-collapse: collapse; width: max-content; min-width: 100%; font-size: 12px; }}
    th, td {{ border-bottom: 1px solid #eceff3; text-align: left; padding: 8px; white-space: nowrap; }}
    .table-wrap {{ overflow: auto; }}
    @media (max-width: 860px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h2>Simulator 可视化面板</h2>
      {err_html}
      <form method="post" action="/run">
        <div class="grid">
          <div><label>Seeds目录</label><input name="seeds_dir" value="{html.escape(defaults['seeds_dir'])}" /></div>
          <div><label>runs (0=每个seed跑1次)</label><input name="runs" value="{defaults['runs']}" /></div>
          <div><label>max_seeds (0=全部)</label><input name="max_seeds" value="{defaults['max_seeds']}" /></div>
          <div><label>entry_fee</label><input name="entry_fee" value="{defaults['entry_fee']}" /></div>
          <div><label>goal_target</label><input name="goal_target" value="{defaults['goal_target']}" /></div>
          <div><label>max_moles (最大奖励对应地鼠数)</label><input name="max_moles" value="{defaults['max_moles']}" /></div>
          <div><label>mole_rate (0~1)</label><input name="mole_rate" value="{defaults['mole_rate']}" /></div>
          <div><label>mole_reward_rate (单鼠奖励系数)</label><input name="mole_reward_rate" value="{defaults['mole_reward_rate']}" /></div>
          <div><label>difficulty</label><select name="difficulty">{diff_select}</select></div>
          <div><label>策略版本</label><select name="policy">{policy_select}</select></div>
          <div><label>action_seconds</label><input name="action_seconds" value="{defaults['action_seconds']}" /></div>
          <div><label>max_actions</label><input name="max_actions" value="{defaults['max_actions']}" /></div>
          <div><label>rng_seed</label><input name="rng_seed" value="{defaults['rng_seed']}" /></div>
        </div>
        <div style="margin-top:10px;">
          <label style="display:flex;align-items:center;gap:8px;font-size:14px;color:#222;margin-top:6px;">
            <input type="checkbox" name="prefer_unique" value="1" {"checked" if defaults.get("prefer_unique") else ""} />
            优先不同初始牌面（不强制）
          </label>
        </div>
        <div class="actions">
          <button class="btn" type="submit" name="mode" value="batch">运行模拟</button>
        </div>
      </form>
    </div>
    {summary_html}
    {table_html}
  </div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    defaults = {}

    def send_html(self, body: str, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        global LAST_CSV, LAST_CSV_NAME
        if self.path == "/download":
            if not LAST_CSV:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{LAST_CSV_NAME}"')
            self.send_header("Content-Length", str(len(LAST_CSV)))
            self.end_headers()
            self.wfile.write(LAST_CSV)
            return
        self.send_html(render_page(self.defaults))

    def do_POST(self):
        global LAST_CSV, LAST_CSV_NAME
        if self.path != "/run":
            self.send_response(404)
            self.end_headers()
            return
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size).decode("utf-8")
        form = {k: v[0] for k, v in parse_qs(raw).items()}

        defaults = {
            "seeds_dir": form.get("seeds_dir", self.defaults["seeds_dir"]),
            "runs": to_int(form.get("runs", str(self.defaults["runs"])), self.defaults["runs"]),
            "max_seeds": to_int(form.get("max_seeds", str(self.defaults["max_seeds"])), self.defaults["max_seeds"]),
            "entry_fee": to_float(form.get("entry_fee", str(self.defaults["entry_fee"])), self.defaults["entry_fee"]),
            "goal_target": to_int(form.get("goal_target", str(self.defaults["goal_target"])), self.defaults["goal_target"]),
            "max_moles": to_int(form.get("max_moles", str(self.defaults["max_moles"])), self.defaults["max_moles"]),
            "mole_rate": to_float(form.get("mole_rate", str(self.defaults["mole_rate"])), self.defaults["mole_rate"]),
            "mole_reward_rate": to_float(form.get("mole_reward_rate", str(self.defaults["mole_reward_rate"])), self.defaults["mole_reward_rate"]),
            "difficulty": (form.get("difficulty", self.defaults["difficulty"]) or "D5").strip(),
            "policy": normalize_policy((form.get("policy", self.defaults["policy"]) or DEFAULT_POLICY).strip().lower()),
            "action_seconds": to_float(form.get("action_seconds", str(self.defaults["action_seconds"])), self.defaults["action_seconds"]),
            "max_actions": to_int(form.get("max_actions", str(self.defaults["max_actions"])), self.defaults["max_actions"]),
            "rng_seed": to_int(form.get("rng_seed", str(self.defaults["rng_seed"])), self.defaults["rng_seed"]),
            "prefer_unique": form.get("prefer_unique", "0") == "1",
        }
        self.defaults = defaults

        try:
            t0 = time.perf_counter()
            seed_cases = load_seed_cases(Path(defaults["seeds_dir"]), defaults["max_seeds"])
            seed_cases = build_seed_pool(seed_cases, defaults["difficulty"], defaults["prefer_unique"])
            if not seed_cases:
                raise ValueError("没有可用seed（请检查目录/难度筛选）")

            rng = random.Random(defaults["rng_seed"])

            rows = []
            runs = defaults["runs"]
            if runs > 0:
                for sc in build_run_seed_list(seed_cases, runs, rng):
                    rows.append(
                        simulate(
                            sc,
                            rng,
                            defaults["entry_fee"],
                            defaults["action_seconds"],
                            defaults["max_actions"],
                            defaults["goal_target"],
                            defaults["max_moles"],
                            defaults["mole_rate"],
                            defaults["policy"],
                            False,
                            defaults["mole_reward_rate"],
                        )
                    )
            else:
                for sc in seed_cases:
                    rows.append(
                        simulate(
                            sc,
                            rng,
                            defaults["entry_fee"],
                            defaults["action_seconds"],
                            defaults["max_actions"],
                            defaults["goal_target"],
                            defaults["max_moles"],
                            defaults["mole_rate"],
                            defaults["policy"],
                            False,
                            defaults["mole_reward_rate"],
                        )
                    )

            elapsed = time.perf_counter() - t0
            LAST_CSV = build_csv(rows)
            LAST_CSV_NAME = "sim_results.csv"
            self.send_html(render_page(defaults, summarize(rows, elapsed), rows))
        except Exception as e:
            self.send_html(render_page(defaults, error=str(e)), status=400)


def main():
    ap = argparse.ArgumentParser(description="Simple local web UI for simulator.py")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--seeds-dir", default="/Users/chase.wang/ugx_block_seed/Data/ExportSeeds")
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--max-seeds", type=int, default=10000)
    ap.add_argument("--entry-fee", type=float, default=1.0)
    ap.add_argument("--goal-target", type=int, default=6)
    ap.add_argument("--max-moles", type=int, default=10)
    ap.add_argument("--mole-rate", type=float, default=0.40)
    ap.add_argument("--mole-reward-rate", type=float, default=MOLE_REWARD_RATE)
    ap.add_argument("--difficulty", default="D5")
    ap.add_argument("--policy", default=DEFAULT_POLICY)
    ap.add_argument(
        "--prefer-unique",
        dest="prefer_unique",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    ap.add_argument("--action-seconds", type=float, default=2.0)
    ap.add_argument("--max-actions", type=int, default=150)
    ap.add_argument("--rng-seed", type=int, default=20260302)
    args = ap.parse_args()

    Handler.defaults = {
        "seeds_dir": args.seeds_dir,
        "runs": args.runs,
        "max_seeds": args.max_seeds,
        "entry_fee": args.entry_fee,
        "goal_target": args.goal_target,
        "max_moles": args.max_moles,
        "mole_rate": args.mole_rate,
        "mole_reward_rate": args.mole_reward_rate,
        "difficulty": args.difficulty,
        "policy": normalize_policy(args.policy),
        "action_seconds": args.action_seconds,
        "max_actions": args.max_actions,
        "rng_seed": args.rng_seed,
        "prefer_unique": args.prefer_unique,
    }
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Simulator UI: http://{args.host}:{args.port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
