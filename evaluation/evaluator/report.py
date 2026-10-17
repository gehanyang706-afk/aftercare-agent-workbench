"""No cherry picking: all attempted tasks, failures and unknown usage stay in reports."""

import csv
import io
import json


def render(summary, directory):
    table = io.StringIO()
    columns = [
        "scenario_id",
        "category",
        "success",
        "state_ok",
        "process_ok",
        "communication_ok",
        "system_error",
        "latency_seconds",
    ]
    writer = csv.DictWriter(table, fieldnames=columns)
    writer.writeheader()
    for row in summary["tasks"]:
        writer.writerow(
            {
                "scenario_id": row["scenario_id"],
                "category": row["category"],
                "latency_seconds": row["latency_seconds"],
                **{key: row["result"][key] for key in columns[2:-1]},
            }
        )
    (directory / "report.csv").write_text(table.getvalue())
    lines = [
        "# 离线开发评测",
        "",
        f"配置：{summary['profile']}；脚本模型；真实 API 请求 0。",
        "",
        f"Task Success：{summary['passed_tasks']}/{summary['attempted_tasks']}。",
        f"可办理任务完成：{summary['eligible_completed']}/{summary['eligible_tasks']}。",
        f"会话 {summary['conversations']}，脚本模型请求 {summary['synthetic_model_calls']}。",
        "",
        "| 分类 | 通过/尝试 |",
        "|---|---:|",
    ]
    for category, count in summary["categories"].items():
        lines.append(f"| {category} | {count['passed']}/{count['attempted']} |")
    lines.extend(
        [
            "",
            "失败保留在 JSON/CSV。模拟 usage 不是供应商 Token 或费用。",
            "",
            *["- " + limitation for limitation in summary["limitations"]],
        ]
    )
    (directory / "report.md").write_text("\n".join(lines) + "\n")
    (directory / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
