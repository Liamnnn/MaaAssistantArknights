"""从 Dr-hydra/MaaAssistantArknights 的 resource/SPAFarm/ 生成内置赛季数据。

用法：
    git clone --depth 1 -b pr/spa-badge-farm https://github.com/Dr-hydra/MaaAssistantArknights
    python tools/import_spafarm_data.py --spa-repo path/to/MaaAssistantArknights

数据来源为游戏数据（torappu/PRTS），上游扩展为 GPL-3.0-or-later；本仓库按 AGPL-3.0 使用。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GOALS = [
    {"id": "task-1", "label": "炎 / 莱塔尼亚 / 奥术", "bonds": ["炎", "莱塔尼亚", "奥术"], "layers": 100},
    {"id": "task-2", "label": "阿戈尔 / 卡西米尔 / 突袭", "bonds": ["阿戈尔", "卡西米尔", "突袭"], "layers": 100},
    {"id": "task-3", "label": "叙拉古 / 萨尔贡 / 精准", "bonds": ["叙拉古", "萨尔贡", "精准"], "layers": 100},
    {"id": "task-4", "label": "维多利亚 / 谢拉格 / 灵巧", "bonds": ["维多利亚", "谢拉格", "灵巧"], "layers": 100},
    {"id": "task-5", "label": "乌萨斯 / 伊比利亚 / 聚合", "bonds": ["乌萨斯", "伊比利亚", "聚合"], "layers": 100},
    {"id": "task-6", "label": "奇迹 / 远见 / 投资人", "bonds": ["奇迹", "远见", "投资人"], "layers": 50},
    {"id": "task-7", "label": "迅捷 / 不屈 / 坚守 / 助力", "bonds": ["迅捷", "不屈", "坚守", "助力"], "layers": 50},
]


def is_stacker(chess: dict) -> bool:
    return any("层数+" in (t.get("text") or "") for t in chess.get("traits") or [])


def build(spa_repo: Path) -> dict:
    data = spa_repo / "resource" / "SPAFarm"
    farm = json.loads((data / "farm-rules.json").read_text(encoding="utf-8"))
    bonds = json.loads((data / "bonds.json").read_text(encoding="utf-8"))
    chess = json.loads((data / "chess.json").read_text(encoding="utf-8"))
    meta = json.loads((data / "meta.json").read_text(encoding="utf-8"))
    return {
        "meta": {
            "season": meta.get("season"),
            "name": meta.get("name"),
            "version": meta.get("version"),
            "data_version": meta.get("dataVersion"),
            "source": "Dr-hydra/MaaAssistantArknights resource/SPAFarm (game data via torappu/PRTS)",
            "generated_by": "tools/import_spafarm_data.py",
        },
        "strategies": [
            {"id": s["id"], "name": s["name"], "type": s["type"], "available": bool(s["available"])}
            for s in farm["strategies"]
        ],
        "bonds": [{"id": b["bondId"], "name": b["name"], "core": bool(b.get("isCore"))} for b in bonds],
        "chess": [
            {
                "name": c["name"],
                "tier": c["tier"],
                "price": c.get("price", 0),
                "bonds": c.get("bondNames", []),
                "stacker": is_stacker(c),
            }
            for c in chess
        ],
        "goals": GOALS,
        "etchings": {
            "total_wins": 60,
            "strategies_with_badge": 20,
            "per_strategy_clears": 3,
            "core_bond_layers": 300,
            "prerequisite_badges": 9,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spa-repo", required=True, help="MaaAssistantArknights fork 的本地路径")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "spa_farm" / "data" / "season_regulation.json"),
    )
    args = parser.parse_args()
    payload = build(Path(args.spa_repo))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(payload['strategies'])} strategies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
