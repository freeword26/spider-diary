import datetime
import logging
import os
import pathlib
import socket

logger = logging.getLogger(__name__)

VERSION = "1.0.0"


class ReportGenerator:

    def __init__(self, output_dir=None):
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), "reports")
        self.output_dir = pathlib.Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("ReportGenerator initialized: output_dir=%s", self.output_dir)

    def _determine_risk_level(self, system_data):
        status = system_data.get("overall_status", "ok")
        risk_map = {
            "ok": "低 / Low",
            "warning": "中 / Medium",
            "critical": "高 / High",
        }
        return risk_map.get(status, "低 / Low")

    def _generate_advice(self, system_data, issues):
        advice = []
        disk = system_data.get("disk", {})
        memory = system_data.get("memory", {})
        load = system_data.get("load", {})

        if disk.get("status") in ("warning", "critical"):
            advice.append(
                f"- **磁盘空间紧张** [{disk['status'].upper()}]: 当前使用率 {disk.get('percent', 'N/A')}%，"
                f"建议清理不必要的文件以释放空间。"
            )
        if memory.get("status") in ("warning", "critical"):
            advice.append(
                f"- **内存使用率较高** [{memory['status'].upper()}]: 当前使用率 {memory.get('percent', 'N/A')}%，"
                f"建议关闭不必要的进程或增加物理内存。"
            )
        cpu_percent = load.get("cpu_percent", 0)
        if isinstance(cpu_percent, (int, float)) and cpu_percent > 80:
            advice.append(
                f"- **CPU 负载较高** [{load.get('status', 'ok').upper()}]: 当前使用率 {cpu_percent}%，"
                f"建议检查高 CPU 占用的进程。"
            )
        if issues:
            advice.append(
                f"- **关注项目问题**: 当前有 {len(issues)} 个问题需要处理，建议优先处理高风险项。"
            )
        if not advice:
            advice.append("- 系统运行正常，暂无特殊运维建议。继续监控即可。")
        return "\n".join(advice)

    def _generate_summary(self, system_data, project_data, issues):
        status_label = {
            "ok": "正常",
            "warning": "警告",
            "critical": "严重",
        }
        overall = system_data.get("overall_status", "ok")
        risk = self._determine_risk_level(system_data)
        parts = [
            f"- **系统总体状态**: {status_label.get(overall, overall)} (风险等级: {risk})",
            f"- **项目概况**: 共 {project_data.get('total', 0)} 个项目，"
            f" {project_data.get('active', 0)} 个活跃项目，"
            f"整体进度 {project_data.get('progress_pct', 0)}%",
        ]
        if issues:
            parts.append(f"- **待处理问题**: {len(issues)} 项，建议尽快跟进。")
        else:
            parts.append("- **待处理问题**: 无")
        return "\n".join(parts)

    def _render_issues(self, issues):
        if not issues:
            return "无未解决的问题。"
        lines = []
        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. {issue}")
        return "\n".join(lines)

    def _render_project_table(self, projects):
        if not projects:
            return "_无项目记录_"
        header = "| 项目ID | 项目名称 | 状态 | 进度 |\n|--------|---------|------|------|\n"
        rows = []
        for p in projects:
            pid = p.get("id", "")
            name = p.get("name", "")
            status = p.get("status", "")
            progress = p.get("progress", 0)
            rows.append(f"| {pid} | {name} | {status} | {progress}% |")
        return header + "\n".join(rows)

    def generate(self, system_data, project_data, issues):
        ts = system_data.get("timestamp", datetime.datetime.now().isoformat())
        hostname = system_data.get("hostname", socket.gethostname())

        try:
            dt = datetime.datetime.fromisoformat(ts)
            date_str = dt.strftime("%Y-%m-%d")
            timestamp_display = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            timestamp_display = ts

        disk = system_data.get("disk", {})
        memory = system_data.get("memory", {})
        processes = system_data.get("processes", {})
        load = system_data.get("load", {})
        overall_status = system_data.get("overall_status", "ok")
        risk_level = self._determine_risk_level(system_data)

        projects = project_data.get("projects", [])
        total = project_data.get("total", len(projects))
        tasks = project_data.get("tasks", 0)
        done = project_data.get("done", 0)
        doing = project_data.get("doing", 0)
        active = project_data.get("active", 0)
        progress_pct = project_data.get("progress_pct", 0)

        issues_section = self._render_issues(issues)
        advice_section = self._generate_advice(system_data, issues)
        summary_section = self._generate_summary(system_data, project_data, issues)
        project_table = self._render_project_table(projects)

        content = f"""# 每日运维报告 / Daily Ops Report

**生成时间**: {timestamp_display}
**主机**: {hostname}
**报告周期**: {date_str}

## 1. 系统状态检查

### 1.1 总体状态
- **状态**: {overall_status}
- **风险等级**: {risk_level}

### 1.2 磁盘空间
- **路径**: {disk.get('path', 'N/A')}
- **总容量**: {disk.get('total_gb', 'N/A')} GB
- **已使用**: {disk.get('used_gb', 'N/A')} GB ({disk.get('percent', 'N/A')}%)
- **可用**: {disk.get('free_gb', 'N/A')} GB
- **状态**: {disk.get('status', 'N/A')}

### 1.3 内存使用
- **总内存**: {memory.get('total_gb', 'N/A')} GB
- **已使用**: {memory.get('used_gb', 'N/A')} GB ({memory.get('percent', 'N/A')}%)
- **可用**: {memory.get('available_gb', 'N/A')} GB
- **状态**: {memory.get('status', 'N/A')}

### 1.4 进程状态
- **运行进程数**: {processes.get('count', 'N/A')}
- **状态**: {processes.get('status', 'N/A')}

## 2. 项目状态总览
- **项目总数**: {total}
- **任务总数**: {tasks}
- **已完成**: {done}
- **进行中**: {doing}
- **活跃项目**: {active}
- **整体进度**: {progress_pct}%

### 2.1 项目详情
{project_table}

## 3. 发现的问题
{issues_section}

## 4. 运维建议
{advice_section}

## 5. 总结
{summary_section}

---
*Generated by Spider Diary v{VERSION}*
"""

        report_data = {
            "report_path": None,
            "content": content,
            "timestamp": ts,
        }
        return report_data

    def save(self, report_data):
        content = report_data.get("content", "")
        ts = report_data.get("timestamp", datetime.datetime.now().isoformat())

        try:
            dt = datetime.datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            dt = datetime.datetime.now()

        date_str = dt.strftime("%Y-%m-%d")
        dated_path = self.output_dir / f"每日运维报告_{date_str}.md"
        latest_path = self.output_dir / "latest.md"

        dated_path.write_text(content, encoding="utf-8")
        latest_path.write_text(content, encoding="utf-8")

        report_data["report_path"] = str(dated_path)
        logger.info("Report saved: %s", dated_path)
        logger.info("Report saved: %s", latest_path)

        return str(dated_path)

    def generate_and_save(self, system_data, project_data, issues):
        report_data = self.generate(system_data, project_data, issues)
        self.save(report_data)
        return report_data
