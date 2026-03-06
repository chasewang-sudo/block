#!/usr/bin/env python3
import argparse
import html
import json
import mimetypes
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

from simulator import (
    DEFAULT_POLICY,
    DEFAULT_MOLE_MODE,
    MOLE_MODE_FLAT,
    MOLE_MODE_GUARDRAILS,
    MOLE_MODE_SEGMENT_V3,
    MOLE_MODE_SEGMENT_V4,
    MOLE_MODE_SEGMENT_V5,
    MOLE_MODE_SEGMENT_CUSTOM,
    MOLE_MODE_UNIFORM_SMOOTH,
    MOLE_MODE_UNIFORM_BALANCED,
    MOLE_MODES,
    MOLE_REWARD_RATE,
    build_run_seed_list,
    build_seed_pool,
    load_seed_cases,
    parse_difficulty,
    normalize_policy,
    policy_display_name,
    simulate,
)


LAST_CSV = b""
LAST_CSV_NAME = "sim_results.csv"
RUN_JOBS = {}
RUN_JOBS_LOCK = threading.Lock()


def build_seed_file_index(seeds_dir: Path):
    files_by_diff = {}
    all_files = []
    for p in seeds_dir.glob("*.jsonl"):
        diff = parse_difficulty(p.stem).upper()
        files_by_diff.setdefault(diff, []).append(p)
        all_files.append(p)
    return {"all": all_files, "by_diff": files_by_diff}


def read_seed_case_from_file(path: Path):
    with path.open("r", encoding="utf-8") as f:
        line = f.readline().strip()
        if not line:
            return None
        d = json.loads(line)
    return {
        "file": path.name,
        "name": d.get("case_hash", path.stem),
        "initialGrid": d.get("initial_grid", [0] * 8),
        "blockIds": [x.get("block_id") for x in d.get("block_sequence", []) if x.get("block_id")],
        "difficulty": parse_difficulty(path.stem).upper(),
    }

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
    "moleMode": "覆盖率模式",
    "moleDistribution": "覆盖率分布模式",
    "moleCoverage": "鼹鼠覆盖率(0~1)",
    "moleRewardRate": "单鼠奖励系数",
    "rewardPerMoleDollar": "单鼠奖励金额($)",
    "moleGuardrails": "鼹鼠生成干预开关",
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
    "moleMode",
    "moleDistribution",
    "moleRewardRate",
    "rewardPerMoleDollar",
    "moleGuardrails",
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

CONCISE_FIELDS = [
    "seed",
    "difficulty",
    "maxAliveMoles",
    "maxNoMolePlaceStreak",
    "earned",
    "remainingTime",
    "result",
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


def ordered_fields(rows, concise_report: bool = False):
    if not rows:
        return []
    if concise_report:
        keys = list(rows[0].keys())
        return [k for k in CONCISE_FIELDS if k in keys]
    keys = list(rows[0].keys())
    ordered = [k for k in PREFERRED_FIELD_ORDER if k in keys]
    ordered.extend([k for k in keys if k not in ordered])
    return ordered


def build_csv(rows, concise_report: bool = False):
    if not rows:
        return b""
    header = ordered_fields(rows, concise_report)
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
        return {
            "matches": 0,
            "win_rate": 0.0,
            "rtp": 0.0,
            "stake": 0.0,
            "earned": 0.0,
            "duration_seconds": duration_seconds,
            "by_difficulty": [],
        }
    stake = sum(r["stake"] for r in rows)
    earned = sum(r["earned"] for r in rows)
    win = sum(1 for r in rows if r["result"] != "Fail")
    by_diff = {}
    for row in rows:
        diff = str(row.get("difficulty", "Unknown"))
        by_diff.setdefault(diff, []).append(row)
    by_difficulty = []
    for diff in sorted(by_diff.keys()):
        diff_rows = by_diff[diff]
        diff_stake = sum(r["stake"] for r in diff_rows)
        diff_earned = sum(r["earned"] for r in diff_rows)
        diff_win = sum(1 for r in diff_rows if r["result"] != "Fail")
        by_difficulty.append(
            {
                "difficulty": diff,
                "matches": len(diff_rows),
                "win_rate": (diff_win / len(diff_rows)) if diff_rows else 0.0,
                "rtp": (diff_earned / diff_stake) if diff_stake > 0 else 0.0,
                "stake": diff_stake,
                "earned": diff_earned,
            }
        )
    return {
        "matches": len(rows),
        "win_rate": win / len(rows),
        "rtp": (earned / stake) if stake > 0 else 0.0,
        "stake": stake,
        "earned": earned,
        "duration_seconds": duration_seconds,
        "by_difficulty": by_difficulty,
    }


def render_progress_page(defaults, job_id: str):
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Simulator Progress</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f5f6f8; color: #111; }}
    .wrap {{ max-width: 760px; margin: 32px auto; padding: 0 16px 32px; }}
    .card {{ background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 6px 24px rgba(0,0,0,.08); }}
    .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; font-size: 14px; color: #445; }}
    .bar {{ margin-top: 18px; height: 14px; border-radius: 999px; background: #e7ebf0; overflow: hidden; }}
    .bar-fill {{ height: 100%; width: 0%; background: linear-gradient(90deg, #32b46c, #0d6efd); transition: width .18s ease; }}
    .status {{ margin-top: 14px; font-size: 15px; font-weight: 600; color: #223; }}
    .sub {{ margin-top: 8px; font-size: 13px; color: #667; }}
    .timing {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; font-size: 13px; color: #556; }}
    .error {{ margin-top: 14px; padding: 12px 14px; border-radius: 12px; background: #ffe7e7; color: #b00020; display:none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h2>模拟进行中</h2>
      <div class="sub">任务 ID: {html.escape(job_id)}</div>
      <div class="meta">
        <div>难度: <b>{html.escape(str(defaults.get("difficulty", "D5")))}</b></div>
        <div>模式: <b>{html.escape(str(defaults.get("mole_mode", DEFAULT_MOLE_MODE)))}</b></div>
        <div>runs: <b>{html.escape(str(defaults.get("runs", 0)))}</b></div>
        <div>策略: <b>{html.escape(str(defaults.get("policy", DEFAULT_POLICY)))}</b></div>
      </div>
      <div class="bar"><div id="bar-fill" class="bar-fill"></div></div>
      <div id="status" class="status">准备中...</div>
      <div id="sub" class="sub">0 / 0</div>
      <div class="timing">
        <div>已耗时: <b id="elapsed">00:00</b></div>
        <div>预计结束: <b id="eta">计算中...</b></div>
      </div>
      <div id="error" class="error"></div>
    </div>
  </div>
<script>
(() => {{
  const jobId = {json.dumps(job_id)};
  const fillEl = document.getElementById('bar-fill');
  const statusEl = document.getElementById('status');
  const subEl = document.getElementById('sub');
  const elapsedEl = document.getElementById('elapsed');
  const etaEl = document.getElementById('eta');
  const errEl = document.getElementById('error');

  const fmtSeconds = (sec) => {{
    const total = Math.max(0, Math.floor(Number(sec || 0)));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) return `${{String(h).padStart(2, '0')}}:${{String(m).padStart(2, '0')}}:${{String(s).padStart(2, '0')}}`;
    return `${{String(m).padStart(2, '0')}}:${{String(s).padStart(2, '0')}}`;
  }};
  const fmtClock = (epochSec) => {{
    if (!epochSec) return '计算中...';
    const d = new Date(Number(epochSec) * 1000);
    return d.toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }});
  }};

  const tick = async () => {{
    try {{
      const resp = await fetch(`/api/run-status?id=${{encodeURIComponent(jobId)}}`, {{ cache: 'no-store' }});
      if (!resp.ok) throw new Error(`HTTP ${{resp.status}}`);
      const data = await resp.json();
      const total = Math.max(0, Number(data.total || 0));
      const current = Math.max(0, Number(data.current || 0));
      const pct = total > 0 ? Math.max(0, Math.min(100, current / total * 100)) : 0;
      fillEl.style.width = `${{pct}}%`;
      statusEl.textContent = data.status_text || '运行中...';
      subEl.textContent = `${{current}} / ${{total}}`;
      elapsedEl.textContent = fmtSeconds(data.elapsed_seconds || 0);
      etaEl.textContent = fmtClock(data.eta_epoch || 0);
      if (data.state === 'done') {{
        fillEl.style.width = '100%';
        etaEl.textContent = '已完成';
        window.location.href = `/result?id=${{encodeURIComponent(jobId)}}`;
        return;
      }}
      if (data.state === 'error') {{
        errEl.style.display = 'block';
        errEl.textContent = data.error || '模拟失败';
        statusEl.textContent = '运行失败';
        etaEl.textContent = '--';
        return;
      }}
      setTimeout(tick, 250);
    }} catch (err) {{
      errEl.style.display = 'block';
      errEl.textContent = String(err);
      statusEl.textContent = '状态查询失败';
      etaEl.textContent = '--';
    }}
  }};
  tick();
}})();
</script>
</body>
</html>"""


def render_page(defaults, summary=None, rows=None, error=""):
    rows = rows or []
    diff_val = str(defaults.get("difficulty", "D5")).upper()
    policy_val = normalize_policy(str(defaults.get("policy", DEFAULT_POLICY)))
    diff_options = [
        ("D5", "D5"),
        ("Easy", "Easy"),
        ("D0", "D0"),
        ("D1", "D1"),
        ("D2", "D2"),
        ("D3", "D3"),
        ("D4", "D4"),
        ("D6", "D6"),
        ("D7", "D7"),
        ("D8", "D8"),
        ("D9", "D9"),
        ("D10", "D10"),
        ("D11", "D11"),
        ("D12", "D12"),
        ("R13", "R13"),
        ("R14", "R14"),
        ("ALL", "全难度(ALL)"),
    ]
    diff_select = "".join(
        f'<option value="{val}" {"selected" if diff_val == val.upper() else ""}>{label}</option>' for val, label in diff_options
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
    mole_mode_options = [
        (MOLE_MODE_GUARDRAILS, "干预"),
        (MOLE_MODE_FLAT, "不干预"),
        (MOLE_MODE_UNIFORM_SMOOTH, "uniform_smooth (p30,w12,l2,u5)"),
        (MOLE_MODE_UNIFORM_BALANCED, "uniform_balanced"),
        (MOLE_MODE_SEGMENT_V3, "segment_35_30_20_5"),
        (MOLE_MODE_SEGMENT_V4, "segment_25_20_15_5"),
        (MOLE_MODE_SEGMENT_V5, "segment_28_20_12_5"),
        (MOLE_MODE_SEGMENT_CUSTOM, "segment_custom"),
    ]
    mole_mode_val = str(defaults.get("mole_mode", DEFAULT_MOLE_MODE))
    mole_mode_select = "".join(
        f'<option value="{v}" {"selected" if mole_mode_val == v else ""}>{label}</option>' for v, label in mole_mode_options
    )
    summary_html = ""
    if summary:
        by_diff_rows = "".join(
            (
                "<tr>"
                f"<td>{html.escape(str(item['difficulty']))}</td>"
                f"<td>{item['matches']}</td>"
                f"<td>{item['win_rate']:.2%}</td>"
                f"<td>{item['rtp']:.3f}</td>"
                f"<td>${item['stake']:.2f}</td>"
                f"<td>${item['earned']:.2f}</td>"
                "</tr>"
            )
            for item in summary.get("by_difficulty", [])
        )
        by_diff_html = ""
        if by_diff_rows:
            by_diff_html = f"""
            <div style="margin-top:14px">
              <h4 style="margin:0 0 8px">分难度返奖率</h4>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>difficulty</th>
                      <th>对局数</th>
                      <th>胜率</th>
                      <th>RTP</th>
                      <th>总下注</th>
                      <th>总返奖</th>
                    </tr>
                  </thead>
                  <tbody>{by_diff_rows}</tbody>
                </table>
              </div>
            </div>
            """
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
          {by_diff_html}
          <a class="btn" href="/download">下载CSV</a>
        </div>
        """

    concise_report = bool(defaults.get("concise_report", False))
    table_html = ""
    if rows:
        header_fields = ordered_fields(rows, concise_report)
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
          <div id="mole-rate-field"><label>mole_rate (0~1)</label><input id="mole-rate-input" name="mole_rate" value="{defaults['mole_rate']}" /></div>
          <div><label>mole_mode</label><select id="mole-mode-select" name="mole_mode">{mole_mode_select}</select></div>
          <div><label>mole_reward_rate (单鼠奖励系数)</label><input name="mole_reward_rate" value="{defaults['mole_reward_rate']}" /></div>
          <div id="seg-0-2-field"><label>seg_rate_0_2</label><input name="seg_rate_0_2" value="{defaults.get('seg_rate_0_2', 1.0)}" /></div>
          <div id="seg-3-29-field"><label>seg_rate_3_29</label><input name="seg_rate_3_29" value="{defaults.get('seg_rate_3_29', 0.28)}" /></div>
          <div id="seg-30-59-field"><label>seg_rate_30_59</label><input name="seg_rate_30_59" value="{defaults.get('seg_rate_30_59', 0.20)}" /></div>
          <div id="seg-60-89-field"><label>seg_rate_60_89</label><input name="seg_rate_60_89" value="{defaults.get('seg_rate_60_89', 0.12)}" /></div>
          <div id="seg-90p-field"><label>seg_rate_90p</label><input name="seg_rate_90p" value="{defaults.get('seg_rate_90p', 0.05)}" /></div>
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
          <label style="display:flex;align-items:center;gap:8px;font-size:14px;color:#222;margin-top:6px;">
            <input type="checkbox" name="all_balanced" value="1" {"checked" if defaults.get("all_balanced", True) else ""} />
            ALL难度时按难度均衡采样
          </label>
          <label style="display:flex;align-items:center;gap:8px;font-size:14px;color:#222;margin-top:6px;">
            <input type="checkbox" name="concise_report" value="1" {"checked" if defaults.get("concise_report", False) else ""} />
            精简报表模式（仅保留：场上同鼠峰值、连续未出鼠、本局收益、剩余时间、比赛结果）
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
<script>
(() => {{
  const modeEl = document.getElementById('mole-mode-select');
  const rateField = document.getElementById('mole-rate-field');
  const rateInput = document.getElementById('mole-rate-input');
  const segFields = [
    document.getElementById('seg-0-2-field'),
    document.getElementById('seg-3-29-field'),
    document.getElementById('seg-30-59-field'),
    document.getElementById('seg-60-89-field'),
    document.getElementById('seg-90p-field'),
  ];
  const sync = () => {{
    if (!modeEl || !rateField || !rateInput) return;
    const isSegment = modeEl.value === 'segment_35_30_20_5' || modeEl.value === 'segment_25_20_15_5' || modeEl.value === 'segment_28_20_12_5' || modeEl.value === 'segment_custom';
    const isUniformSmooth = modeEl.value === 'uniform_smooth';
    const isCustom = modeEl.value === 'segment_custom';
    rateField.style.display = (isSegment || isUniformSmooth) ? 'none' : '';
    rateInput.disabled = (isSegment || isUniformSmooth);
    segFields.forEach((el) => {{ if (el) el.style.display = isCustom ? '' : 'none'; }});
  }};
  if (modeEl) modeEl.addEventListener('change', sync);
  sync();
}})();
</script>
</html>"""


def run_simulation_job(job_id: str, defaults: dict):
    global LAST_CSV, LAST_CSV_NAME
    try:
        with RUN_JOBS_LOCK:
            RUN_JOBS[job_id]["state"] = "running"
            RUN_JOBS[job_id]["status_text"] = "读取种子..."
            started_at = float(RUN_JOBS[job_id].get("started_at", time.time()))
        t0 = time.perf_counter()
        seed_cases = load_seed_cases(Path(defaults["seeds_dir"]), defaults["max_seeds"])
        seed_cases = build_seed_pool(seed_cases, defaults["difficulty"], defaults["prefer_unique"])
        if not seed_cases:
            raise ValueError("没有可用seed（请检查目录/难度筛选）")

        rng = random.Random(defaults["rng_seed"])
        segment_rates = {
            "r0_2": min(1.0, max(0.0, float(defaults.get("seg_rate_0_2", 1.0)))),
            "r3_29": min(1.0, max(0.0, float(defaults.get("seg_rate_3_29", 0.28)))),
            "r30_59": min(1.0, max(0.0, float(defaults.get("seg_rate_30_59", 0.20)))),
            "r60_89": min(1.0, max(0.0, float(defaults.get("seg_rate_60_89", 0.12)))),
            "r90p": min(1.0, max(0.0, float(defaults.get("seg_rate_90p", 0.05)))),
        }
        rows = []
        runs = defaults["runs"]
        if runs > 0:
            balance_all = defaults["all_balanced"] and str(defaults["difficulty"]).strip().upper() == "ALL"
            run_list = build_run_seed_list(seed_cases, runs, rng, balance_all)
        else:
            run_list = list(seed_cases)

        total = len(run_list)
        with RUN_JOBS_LOCK:
            RUN_JOBS[job_id]["total"] = total
            RUN_JOBS[job_id]["status_text"] = "开始模拟..."

        for idx, sc in enumerate(run_list, start=1):
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
                    defaults["mole_mode"],
                    segment_rates,
                )
            )
            if idx == 1 or idx == total or idx % 5 == 0:
                with RUN_JOBS_LOCK:
                    if job_id in RUN_JOBS:
                        elapsed_now = max(0.0, time.time() - started_at)
                        eta_epoch = 0.0
                        if idx > 0 and total > 0:
                            eta_epoch = time.time() + max(0.0, elapsed_now * (total - idx) / idx)
                        RUN_JOBS[job_id]["current"] = idx
                        RUN_JOBS[job_id]["status_text"] = f"模拟中... ({idx}/{total})"
                        RUN_JOBS[job_id]["elapsed_seconds"] = elapsed_now
                        RUN_JOBS[job_id]["eta_epoch"] = eta_epoch

        elapsed = max(time.perf_counter() - t0, time.time() - started_at)
        concise_report = bool(defaults.get("concise_report", False))
        csv_bytes = build_csv(rows, concise_report)
        csv_name = "sim_results_concise.csv" if concise_report else "sim_results.csv"
        summary = summarize(rows, elapsed)

        with RUN_JOBS_LOCK:
            RUN_JOBS[job_id].update({
                "state": "done",
                "current": total,
                "total": total,
                "status_text": "模拟完成",
                "elapsed_seconds": elapsed,
                "eta_epoch": 0.0,
                "rows": rows,
                "summary": summary,
                "csv_bytes": csv_bytes,
                "csv_name": csv_name,
            })
        LAST_CSV = csv_bytes
        LAST_CSV_NAME = csv_name
    except Exception as e:
        with RUN_JOBS_LOCK:
            if job_id in RUN_JOBS:
                RUN_JOBS[job_id]["state"] = "error"
                RUN_JOBS[job_id]["error"] = str(e)
                RUN_JOBS[job_id]["status_text"] = "模拟失败"
                RUN_JOBS[job_id]["eta_epoch"] = 0.0


class Handler(BaseHTTPRequestHandler):
    defaults = {}
    seed_index = None
    seed_index_dir = None
    workspace_dir = Path(__file__).resolve().parent

    def send_html(self, body: str, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @classmethod
    def get_seed_index(cls):
        seeds_dir = Path(cls.defaults.get("seeds_dir", cls.workspace_dir / "ExportSeeds"))
        if seeds_dir.name != "ExportSeeds" and (seeds_dir / "ExportSeeds").is_dir():
            seeds_dir = seeds_dir / "ExportSeeds"
        if cls.seed_index is None or cls.seed_index_dir != seeds_dir:
            cls.seed_index = build_seed_file_index(seeds_dir)
            cls.seed_index_dir = seeds_dir
        return cls.seed_index

    def do_GET(self):
        global LAST_CSV, LAST_CSV_NAME
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/run-status":
            q = parse_qs(parsed.query or "")
            job_id = (q.get("id", [""])[0] or "").strip()
            with RUN_JOBS_LOCK:
                job = RUN_JOBS.get(job_id)
            if not job:
                self.send_json({"error": "job not found"}, status=404)
                return
            self.send_json({
                "id": job_id,
                "state": job.get("state", "queued"),
                "current": job.get("current", 0),
                "total": job.get("total", 0),
                "status_text": job.get("status_text", ""),
                "elapsed_seconds": job.get("elapsed_seconds", max(0.0, time.time() - float(job.get("started_at", time.time())))),
                "eta_epoch": job.get("eta_epoch", 0.0),
                "error": job.get("error", ""),
            })
            return
        if path == "/result":
            q = parse_qs(parsed.query or "")
            job_id = (q.get("id", [""])[0] or "").strip()
            with RUN_JOBS_LOCK:
                job = RUN_JOBS.get(job_id)
            if not job:
                self.send_html(render_page(self.defaults, error="任务不存在"), status=404)
                return
            if job.get("state") == "error":
                self.send_html(render_page(job.get("defaults", self.defaults), error=job.get("error", "模拟失败")), status=400)
                return
            if job.get("state") != "done":
                self.send_html(render_progress_page(job.get("defaults", self.defaults), job_id))
                return
            self.send_html(render_page(job.get("defaults", self.defaults), job.get("summary"), job.get("rows")))
            return
        if path == "/download":
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
        if path == "/api/seed/random":
            q = parse_qs(parsed.query or "")
            difficulty = (q.get("difficulty", ["D5"])[0] or "D5").strip().upper()
            try:
                idx = self.get_seed_index()
                if difficulty == "ALL":
                    diffs = [d for d, arr in idx["by_diff"].items() if d != "UNKNOWN" and arr]
                    if diffs:
                        pick_diff = random.choice(diffs)
                        files = idx["by_diff"].get(pick_diff, [])
                    else:
                        files = idx["all"]
                else:
                    files = idx["by_diff"].get(difficulty, [])
                if not files:
                    files = idx["all"]
                if not files:
                    self.send_json({"error": "no seed files"}, status=404)
                    return
                pick = random.choice(files)
                case = read_seed_case_from_file(pick)
                if not case:
                    self.send_json({"error": "empty seed file"}, status=404)
                    return
                self.send_json(case)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
                return
        if path in ("/game", "/index.html"):
            game_file = self.workspace_dir / "index.html"
            if not game_file.exists():
                self.send_response(404)
                self.end_headers()
                return
            data = game_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/"):
            rel = path.lstrip("/")
            if rel:
                target = (self.workspace_dir / rel).resolve()
                if str(target).startswith(str(self.workspace_dir)) and target.is_file():
                    mime, _ = mimetypes.guess_type(str(target))
                    data = target.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", mime or "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
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
            "mole_mode": ((form.get("mole_mode", self.defaults["mole_mode"]) or DEFAULT_MOLE_MODE).strip()),
            "seg_rate_0_2": to_float(form.get("seg_rate_0_2", str(self.defaults.get("seg_rate_0_2", 1.0))), self.defaults.get("seg_rate_0_2", 1.0)),
            "seg_rate_3_29": to_float(form.get("seg_rate_3_29", str(self.defaults.get("seg_rate_3_29", 0.28))), self.defaults.get("seg_rate_3_29", 0.28)),
            "seg_rate_30_59": to_float(form.get("seg_rate_30_59", str(self.defaults.get("seg_rate_30_59", 0.20))), self.defaults.get("seg_rate_30_59", 0.20)),
            "seg_rate_60_89": to_float(form.get("seg_rate_60_89", str(self.defaults.get("seg_rate_60_89", 0.12))), self.defaults.get("seg_rate_60_89", 0.12)),
            "seg_rate_90p": to_float(form.get("seg_rate_90p", str(self.defaults.get("seg_rate_90p", 0.05))), self.defaults.get("seg_rate_90p", 0.05)),
            "mole_reward_rate": to_float(form.get("mole_reward_rate", str(self.defaults["mole_reward_rate"])), self.defaults["mole_reward_rate"]),
            "difficulty": (form.get("difficulty", self.defaults["difficulty"]) or "D5").strip(),
            "policy": normalize_policy((form.get("policy", self.defaults["policy"]) or DEFAULT_POLICY).strip().lower()),
            "action_seconds": to_float(form.get("action_seconds", str(self.defaults["action_seconds"])), self.defaults["action_seconds"]),
            "max_actions": to_int(form.get("max_actions", str(self.defaults["max_actions"])), self.defaults["max_actions"]),
            "rng_seed": to_int(form.get("rng_seed", str(self.defaults["rng_seed"])), self.defaults["rng_seed"]),
            "prefer_unique": form.get("prefer_unique", "0") == "1",
            "all_balanced": form.get("all_balanced", "0") == "1",
            "concise_report": form.get("concise_report", "0") == "1",
        }
        if defaults["mole_mode"] not in MOLE_MODES:
            defaults["mole_mode"] = DEFAULT_MOLE_MODE
        self.defaults = defaults

        try:
            job_id = uuid4().hex
            with RUN_JOBS_LOCK:
                RUN_JOBS[job_id] = {
                    "state": "queued",
                    "current": 0,
                    "total": 0,
                    "status_text": "排队中...",
                    "started_at": time.time(),
                    "elapsed_seconds": 0.0,
                    "eta_epoch": 0.0,
                    "error": "",
                    "defaults": dict(defaults),
                    "rows": [],
                    "summary": None,
                    "csv_bytes": b"",
                    "csv_name": "sim_results.csv",
                }
            worker = threading.Thread(target=run_simulation_job, args=(job_id, dict(defaults)), daemon=True)
            worker.start()
            self.send_html(render_progress_page(defaults, job_id))
        except Exception as e:
            self.send_html(render_page(defaults, error=str(e)), status=400)


def main():
    ap = argparse.ArgumentParser(description="Simple local web UI for simulator.py")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--seeds-dir", default="/Users/chase.wang/Documents/New project 13/ExportSeeds")
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--max-seeds", type=int, default=10000)
    ap.add_argument("--entry-fee", type=float, default=1.0)
    ap.add_argument("--goal-target", type=int, default=12)
    ap.add_argument("--max-moles", type=int, default=20)
    ap.add_argument("--mole-rate", type=float, default=0.30)
    ap.add_argument("--mole-mode", default=DEFAULT_MOLE_MODE, choices=sorted(MOLE_MODES))
    ap.add_argument("--seg-rate-0-2", type=float, default=1.0)
    ap.add_argument("--seg-rate-3-29", type=float, default=0.28)
    ap.add_argument("--seg-rate-30-59", type=float, default=0.20)
    ap.add_argument("--seg-rate-60-89", type=float, default=0.12)
    ap.add_argument("--seg-rate-90p", type=float, default=0.05)
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
    ap.add_argument(
        "--all-balanced",
        dest="all_balanced",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = ap.parse_args()

    Handler.defaults = {
        "seeds_dir": args.seeds_dir,
        "runs": args.runs,
        "max_seeds": args.max_seeds,
        "entry_fee": args.entry_fee,
        "goal_target": args.goal_target,
        "max_moles": args.max_moles,
        "mole_rate": args.mole_rate,
        "mole_mode": args.mole_mode,
        "seg_rate_0_2": args.seg_rate_0_2,
        "seg_rate_3_29": args.seg_rate_3_29,
        "seg_rate_30_59": args.seg_rate_30_59,
        "seg_rate_60_89": args.seg_rate_60_89,
        "seg_rate_90p": args.seg_rate_90p,
        "mole_reward_rate": args.mole_reward_rate,
        "difficulty": args.difficulty,
        "policy": normalize_policy(args.policy),
        "action_seconds": args.action_seconds,
        "max_actions": args.max_actions,
        "rng_seed": args.rng_seed,
        "prefer_unique": args.prefer_unique,
        "all_balanced": args.all_balanced,
        "concise_report": False,
    }
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Simulator UI: http://{args.host}:{args.port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
