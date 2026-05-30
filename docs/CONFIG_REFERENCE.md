# 配置参考

> **文档版本**: v1.0
> **创建日期**: 2026-05-30
> **编写人**: OWL (Migration Agent)

---

## 总览

本文档汇总旧系统所有配置选项，并映射到新的 spider_diary CLI 选项。

---

## 1. daily_operations_config.json

**文件路径**: `E:\03_PMO系统\每日运维\config\daily_operations_config.json`
**描述**: 每日运维沟通流程配置

### 1.1 Schedule (调度时间表)

| 时间 | Agent ID | Agent名称 | 主题 | 时长(分钟) | 苏格拉底阶段 |
|------|----------|-----------|------|-----------|-------------|
| 09:00 | humanities-scholar | 文史/语义专家 | 文献管理和知识卡片 | 30 | 觉察、质疑 |
| 09:30 | math-professor | 逻辑/图谱专家 | 知识图谱和逻辑验证 | 30 | 质疑、重构 |
| 10:00 | skill-manager | 技能管理专家 | 技能库和技能树 | 30 | 觉察、验证 |
| 10:30 | learning-hacker | 自动化黑客 | 自动化脚本和向量索引 | 30 | 重构、验证 |
| 14:00 | tech-expert | 技术专家 | 技术实现和优化 | 30 | 质疑、重构 |
| 14:30 | data-scientist | 数据科学家 | 数据分析和建模 | 30 | 觉察、验证 |
| 15:00 | product-manager | 产品经理 | 产品规划和需求 | 30 | 质疑、重构 |
| 15:30 | expert-biz-doctor | 业务专家 | 业务逻辑和流程 | 30 | 觉察、验证 |

**spider_diary CLI 映射**:
```bash
spider-diary schedule add --time 09:00 --agent humanities-scholar --topic "文献管理和知识卡片" --duration 30
spider-diary schedule add --time 09:30 --agent math-professor --topic "知识图谱和逻辑验证" --duration 30
spider-diary schedule add --time 10:00 --agent skill-manager --topic "技能库和技能树" --duration 30
spider-diary schedule add --time 10:30 --agent learning-hacker --topic "自动化脚本和向量索引" --duration 30
spider-diary schedule add --time 14:00 --agent tech-expert --topic "技术实现和优化" --duration 30
spider-diary schedule add --time 14:30 --agent data-scientist --topic "数据分析和建模" --duration 30
spider-diary schedule add --time 15:00 --agent product-manager --topic "产品规划和需求" --duration 30
spider-diary schedule add --time 15:30 --agent expert-biz-doctor --topic "业务逻辑和流程" --duration 30
```

### 1.2 Socratic Questions (苏格拉底式提问)

#### clarifying (澄清性问题)
| Agent | 示例问题 |
|-------|---------|
| general | 你所说的'{concept}'具体指什么？ |
| humanities-scholar | 你所说的'语义准确'具体指什么？ |
| math-professor | 你所说的'逻辑一致'具体指什么？ |
| skill-manager | 你所说的'技能树优化'具体指什么？ |
| learning-hacker | 你所说的'脚本高效'具体指什么？ |

#### probing (探究性问题)
| Agent | 示例问题 |
|-------|---------|
| general | 为什么你认为这个方案是最好的？ |
| humanities-scholar | 为什么你认为这个知识卡片结构是最优的？ |
| math-professor | 为什么你认为这个图谱构建方法是正确的？ |
| skill-manager | 为什么你认为这个技能树结构是合理的？ |
| learning-hacker | 为什么你认为这个自动化脚本是最优的？ |

#### challenging (挑战性问题)
| Agent | 示例问题 |
|-------|---------|
| general | 如果相反的情况成立，会怎样？ |
| humanities-scholar | 如果用户对'语义准确'的理解与你不同，会怎样？ |
| math-professor | 如果这个逻辑推理的前提不成立，会怎样？ |
| skill-manager | 如果这个技能树的结构假设不成立，会怎样？ |
| learning-hacker | 如果这个自动化脚本的假设不成立，会怎样？ |

#### exemplifying (举例性问题)
| Agent | 示例问题 |
|-------|---------|
| general | 能举一个符合这个定义的例子吗？ |
| humanities-scholar | 能举一个符合'语义准确'定义的知识卡片例子吗？ |
| math-professor | 能举一个符合'逻辑一致'定义的图谱例子吗？ |
| skill-manager | 能举一个符合'技能树优化'定义的例子吗？ |
| learning-hacker | 能举一个符合'脚本高效'定义的例子吗？ |

#### guiding (引导性问题)
| Agent | 示例问题 |
|-------|---------|
| general | 或许我们可以从另一个角度思考这个问题？ |
| humanities-scholar | 或许我们可以从用户体验的角度思考知识卡片设计？ |
| math-professor | 或许我们可以从实际应用的角度思考图谱构建？ |
| skill-manager | 或许我们可以从技能成长的角度思考技能树设计？ |
| learning-hacker | 或许我们可以从性能优化的角度思考脚本设计？ |

#### verifying (验证性问题)
| Agent | 示例问题 |
|-------|---------|
| general | 你能举一个例子证明这个新概念有效吗？ |
| humanities-scholar | 你能举一个例子证明这个新的知识卡片设计有效吗？ |
| math-professor | 你能举一个例子证明这个新的图谱构建方法有效吗？ |
| skill-manager | 你能举一个例子证明这个新的技能树设计有效吗？ |
| learning-hacker | 你能举一个例子证明这个新的自动化脚本有效吗？ |

**spider_diary CLI 映射**:
```bash
spider-diary config set --section socratic_questions --key clarifying.general --value "你所说的'{concept}'具体指什么？"
spider-diary config set --section socratic_questions --key probing.general --value "为什么你认为这个方案是最好的？"
# ... (其他问题类似)
```

### 1.3 Evaluation Metrics (评估指标)

| 指标 | 目标值 | 单位 | 描述 |
|------|--------|------|------|
| communication_efficiency | 30 | minutes | 每次沟通的平均时长 |
| problem_discovery_rate | 1 | problems_per_communication | 每次沟通发现的问题数量 |
| cognition_improvement_rate | 80 | percent | Agent形成新认知的比例 |
| action_completion_rate | 70 | percent | 行动计划的完成比例 |
| agent_satisfaction | 4.5 | score | Agent对沟通的满意度（满分5.0） |

**spider_diary CLI 映射**:
```bash
spider-diary config set --section evaluation_metrics --key communication_efficiency.target --value 30
spider-diary config set --section evaluation_metrics --key problem_discovery_rate.target --value 1
spider-diary config set --section evaluation_metrics --key cognition_improvement_rate.target --value 80
spider-diary config set --section evaluation_metrics --key action_completion_rate.target --value 70
spider-diary config set --section evaluation_metrics --key agent_satisfaction.target --value 4.5
```

### 1.4 Follow-up Settings (跟进设置)

| 选项 | 值 | 描述 |
|------|-----|------|
| default_follow_up_days | 3 | 默认跟进天数 |
| reminder_enabled | true | 是否启用提醒 |
| reminder_days_before | 1 | 提前提醒天数 |

**spider_diary CLI 映射**:
```bash
spider-diary config set --section follow_up_settings --key default_follow_up_days --value 3
spider-diary config set --section follow_up_settings --key reminder_enabled --value true
spider-diary config set --section follow_up_settings --key reminder_days_before --value 1
```

### 1.5 Notification Settings (通知设置)

| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用通知 |
| channels | ["email", "log"] | 通知渠道 |
| recipients | ["system-manager@company.com"] | 接收人 |

**spider_diary CLI 映射**:
```bash
spider-diary config set --section notification_settings --key enabled --value true
spider-diary config set --section notification_settings --key channels --value "email,log"
spider-diary config set --section notification_settings --key recipients --value "system-manager@company.com"
```

### 1.6 Logging Settings (日志设置)

| 选项 | 值 | 描述 |
|------|-----|------|
| level | INFO | 日志级别 |
| format | %(asctime)s - %(name)s - %(levelname)s - %(message)s | 日志格式 |
| file_rotation | true | 是否启用日志轮转 |
| max_bytes | 10485760 (10MB) | 单个日志文件最大大小 |
| backup_count | 5 | 保留的备份文件数量 |

**spider_diary CLI 映射**:
```bash
spider-diary config set --section logging_settings --key level --value INFO
spider-diary config set --section logging_settings --key file_rotation --value true
spider-diary config set --section logging_settings --key max_bytes --value 10485760
spider-diary config set --section logging_settings --key backup_count --value 5
```

### 1.7 Report Settings (报告设置)

| 选项 | 值 | 描述 |
|------|-----|------|
| generate_json | true | 生成JSON报告 |
| generate_markdown | true | 生成Markdown报告 |
| generate_html | false | 生成HTML报告 |
| auto_generate | true | 自动生成 |
| generate_time | 17:00 | 生成时间 |

**spider_diary CLI 映射**:
```bash
spider-diary config set --section report_settings --key generate_json --value true
spider-diary config set --section report_settings --key generate_markdown --value true
spider-diary config set --section report_settings --key generate_html --value false
spider-diary config set --section report_settings --key auto_generate --value true
spider-diary config set --section report_settings --key generate_time --value "17:00"
```

---

## 2. project_startup_config.json

**文件路径**: `E:\03_PMO系统\每日运维\config\project_startup_config.json`
**描述**: 多项目启动管理配置
**版本**: 1.0.0

### 2.1 Projects (项目列表)

#### automa_browser_plugin
| 选项 | 值 | 描述 |
|------|-----|------|
| name | Automa浏览器插件本地连接 | 项目名称 |
| path | e:\软件开发\04_新建项目\Automa浏览器插件本地连接 | 项目路径 |
| enabled | true | 是否启用 |
| startup_mode | manual | 启动模式 |
| health_check.endpoint | http://localhost:5000/health | 健康检查端点 |
| health_check.interval_seconds | 60 | 健康检查间隔 |

**启动文件**:
| 文件 | 描述 | 类型 | 端口 |
|------|------|------|------|
| start_server.bat | 启动服务器 | server | 5000 |
| start_receiver.bat | 启动接收器 | receiver | 5001 |
| start_full.bat | 完整启动 | full | 5000, 5001 |

**spider_diary CLI 映射**:
```bash
spider-diary project add --id automa_browser_plugin --name "Automa浏览器插件本地连接" --path "e:\软件开发\04_新建项目\Automa浏览器插件本地连接" --mode manual
spider-diary project healthcheck --id automa_browser_plugin --endpoint "http://localhost:5000/health" --interval 60
```

#### stats_system
| 选项 | 值 | 描述 |
|------|-----|------|
| name | 统计数据系统 | 项目名称 |
| path | e:\统计数据系统 | 项目路径 |
| enabled | true | 是否启用 |
| startup_mode | automatic | 启动模式 |
| health_check.endpoint | http://localhost:5004/api/health | 健康检查端点 |
| health_check.interval_seconds | 60 | 健康检查间隔 |

**启动文件**: main.py (port 5004)

**spider_diary CLI 映射**:
```bash
spider-diary project add --id stats_system --name "统计数据系统" --path "e:\统计数据系统" --mode automatic
spider-diary project healthcheck --id stats_system --endpoint "http://localhost:5004/api/health" --interval 60
```

#### lqm_framework
| 选项 | 值 | 描述 |
|------|-----|------|
| name | LQM轻量级微服务框架 | 项目名称 |
| path | e:\LQM微服务框架 | 项目路径 |
| enabled | true | 是否启用 |
| startup_mode | automatic | 启动模式 |
| health_check.endpoint | http://localhost:8000/health | 健康检查端点 |
| health_check.interval_seconds | 60 | 健康检查间隔 |

**启动文件**: main.py (port 8000)

**spider_diary CLI 映射**:
```bash
spider-diary project add --id lqm_framework --name "LQM轻量级微服务框架" --path "e:\LQM微服务框架" --mode automatic
spider-diary project healthcheck --id lqm_framework --endpoint "http://localhost:8000/health" --interval 60
```

#### main_project
| 选项 | 值 | 描述 |
|------|-----|------|
| name | 主项目软件开发 | 项目名称 |
| path | e:\软件开发 | 项目路径 |
| enabled | true | 是否启用 |
| startup_mode | automatic | 启动模式 |
| health_check.interval_seconds | 300 | 健康检查间隔 |

**启动文件**: start_daily_ops.bat (daily, 09:00)

**spider_diary CLI 映射**:
```bash
spider-diary project add --id main_project --name "主项目软件开发" --path "e:\软件开发" --mode automatic
spider-diary project schedule --id main_project --script "start_daily_ops.bat" --cron "0 9 * * *"
```

### 2.2 Schedule (调度配置)

#### daily_startup (每日启动)
| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用 |
| time | 09:00 | 启动时间 |
| sequence | stats_system → lqm_framework → main_project | 启动顺序 |

**spider_diary CLI 映射**:
```bash
spider-diary startup schedule --time "09:00" --sequence "stats_system,lqm_framework,main_project"
```

#### daily_shutdown (每日关闭)
| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用 |
| time | 18:00 | 关闭时间 |
| graceful | true | 优雅关闭 |
| timeout_seconds | 30 | 超时时间 |

**spider_diary CLI 映射**:
```bash
spider-diary shutdown schedule --time "18:00" --graceful --timeout 30
```

### 2.3 Monitoring (监控配置)

| 选项 | 值 | 描述 |
|------|-----|------|
| process_check_interval_seconds | 300 | 进程检查间隔 |
| auto_restart_on_failure | true | 失败时自动重启 |
| max_restart_attempts | 3 | 最大重启次数 |
| restart_cooldown_seconds | 60 | 重启冷却时间 |

**spider_diary CLI 映射**:
```bash
spider-diary monitor config --check-interval 300 --auto-restart --max-restart 3 --cooldown 60
```

---

## 3. daily_ops_config.json

**文件路径**: `E:\03_PMO系统\每日运维\config\daily_ops_config.json`
**描述**: 每日运维监控配置
**版本**: 2.2.0

### 3.1 PMO Coordinator (PMO协调者)

| 选项 | 值 | 描述 |
|------|-----|------|
| name | System Manager Agent | Agent名称 |
| agent_id | system-manager | Agent ID |
| permission_level | 4 | 权限级别 |
| role | 总协调者 | 角色 |
| responsibilities | 流程调度、问题升级决策、资源协调、报告汇总 | 职责 |

**spider_diary CLI 映射**:
```bash
spider-diary agent register --id system-manager --name "System Manager Agent" --level 4 --role "总协调者"
```

### 3.2 Schedule (调度时间表)

与 daily_operations_config.json 的 schedule 基本相同，差异如下:

| 时间 | Agent | 主题 | 苏格拉底阶段 | 权限级别 |
|------|-------|------|-------------|----------|
| 10:00 | skill-manager | 技能库刷新和依赖检查 | 觉察、分析 | 3 |
| 10:30 | learning-hacker | 智能路由和模型监控 | 探索、反思 | 2 |

### 3.3 Monitoring (监控配置)

#### skill_library (技能库监控)
| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用 |
| check_interval_minutes | 60 | 检查间隔 |
| path | e:\软件开发\skill_library | 技能库路径 |
| auto_refresh_cache | true | 自动刷新缓存 |
| validate_dependencies | true | 验证依赖 |
| alert_thresholds.skill_error_rate | 0.05 | 技能错误率阈值 |
| alert_thresholds.dependency_broken | 0 | 依赖损坏阈值 |
| alert_thresholds.cache_stale_hours | 24 | 缓存过期小时数 |

**spider_diary CLI 映射**:
```bash
spider-diary monitor skill-library --enabled --interval 60 --path "e:\软件开发\skill_library" --auto-refresh --validate-deps
spider-diary monitor skill-library thresholds --error-rate 0.05 --dependency-broken 0 --cache-stale 24
```

#### model (模型监控)
| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用 |
| check_interval_minutes | 15 | 检查间隔 |
| ollama_endpoint | http://localhost:11434 | Ollama端点 |
| health_check | true | 健康检查 |
| auto_restart | true | 自动重启 |
| alert_thresholds.response_time_ms | 5000 | 响应时间阈值 |
| alert_thresholds.error_rate | 0.05 | 错误率阈值 |

**spider_diary CLI 映射**:
```bash
spider-diary monitor model --enabled --interval 15 --endpoint "http://localhost:11434" --health-check --auto-restart
spider-diary monitor model thresholds --response-time 5000 --error-rate 0.05
```

#### router (路由监控)
| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用 |
| check_interval_minutes | 30 | 检查间隔 |
| alert_thresholds.route_error_rate | 0.03 | 路由错误率阈值 |

**spider_diary CLI 映射**:
```bash
spider-diary monitor router --enabled --interval 30 --error-rate 0.03
```

### 3.4 Unattended Workflows (无人值守工作流)

| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用 |
| systems | 统计数据系统、主项目 | 系统列表 |
| total_workflows | 15 | 工作流总数 |
| scheduled_agents | 7个Agent | 调度Agent列表 |

**spider_diary CLI 映射**:
```bash
spider-diary workflow enable --systems "统计数据系统,主项目" --agents "data-scientist,skill-manager,system-manager,learning-hacker,tech-expert,langchain-orchestrator,humanities-scholar"
```

### 3.5 Reporting (报告配置)

| 选项 | 值 | 描述 |
|------|-----|------|
| generate_json | true | 生成JSON报告 |
| generate_markdown | true | 生成Markdown报告 |
| auto_generate | true | 自动生成 |
| generate_time | 17:00 | 生成时间 |
| output_path | e:\软件开发\系统桌面\PMO系统\每日运维\reports | 输出路径 |

**spider_diary CLI 映射**:
```bash
spider-diary report config --json --markdown --auto --time "17:00" --output "e:\软件开发\系统桌面\PMO系统\每日运维\reports"
```

---

## 4. unattended_workflow_config.json

**文件路径**: `E:\03_PMO系统\每日运维\config\unattended_workflow_config.json`
**描述**: 无人值守工作流调度器配置
**版本**: 2.1.0

### 4.1 Permission Levels (权限级别)

| 级别 | Agents |
|------|--------|
| Level 4 (最高) | system-manager |
| Level 3 (高) | tech-expert, data-scientist, skill-manager, langchain-orchestrator, devops, project-manager |
| Level 2 (中) | learning-hacker, humanities-scholar, trend-forecast, expert-biz-doctor, memory-butler, master-mentor, math-professor, product-manager, developer, business, qa, analyst |

**spider_diary CLI 映射**:
```bash
spider-diary permission set --level 4 --agents "system-manager"
spider-diary permission set --level 3 --agents "tech-expert,data-scientist,skill-manager,langchain-orchestrator,devops,project-manager"
spider-diary permission set --level 2 --agents "learning-hacker,humanities-scholar,trend-forecast,expert-biz-doctor,memory-butler,master-mentor,math-professor,product-manager,developer,business,qa,analyst"
```

### 4.2 Ports (端口配置)

| 系统 | 端口 |
|------|------|
| 统计数据系统 | 5004 |
| 主项目 | 5005 |

**spider_diary CLI 映射**:
```bash
spider-diary port assign --system "统计数据系统" --port 5004
spider-diary port assign --system "主项目" --port 5005
```

### 4.3 Global Settings (全局设置)

| 选项 | 值 | 描述 |
|------|-----|------|
| scheduler_type | APScheduler | 调度器类型 |
| max_workers | 4 | 最大工作线程数 |
| job_defaults.coalesce | false | 合并错过的任务 |
| job_defaults.max_instances | 1 | 最大实例数 |

**spider_diary CLI 映射**:
```bash
spider-diary scheduler config --type APScheduler --max-workers 4 --coalesce false --max-instances 1
```

### 4.4 Notification (通知配置)

| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用 |
| channels | log, file | 通知渠道 |

**spider_diary CLI 映射**:
```bash
spider-diary notification config --enabled --channels "log,file"
```

### 4.5 Permission Validation (权限验证)

| 选项 | 值 | 描述 |
|------|-----|------|
| enabled | true | 是否启用 |
| strict_mode | true | 严格模式 |
| require_approval_for_level_4 | true | Level 4需要审批 |

**spider_diary CLI 映射**:
```bash
spider-diary permission validation --enabled --strict --level4-approval
```

---

## 5. 部署配置 (来自部署指南.md)

### 5.1 服务器配置

| 选项 | 值 | 描述 |
|------|-----|------|
| host | 0.0.0.0 | 监听地址 |
| port | 8000 | 监听端口 |
| workers | 4 | 工作进程数 |

**spider_diary CLI 映射**:
```bash
spider-diary server config --host 0.0.0.0 --port 8000 --workers 4
```

### 5.2 性能配置

| 选项 | 值 | 描述 |
|------|-----|------|
| max_workers | 20 | 最大工作线程 |
| task_timeout | 300 | 任务超时(秒) |
| connection_pool_size | 50 | 连接池大小 |
| cache_enabled | true | 启用缓存 |
| cache_ttl | 3600 | 缓存TTL(秒) |

**spider_diary CLI 映射**:
```bash
spider-diary performance config --max-workers 20 --task-timeout 300 --pool-size 50 --cache --cache-ttl 3600
```

### 5.3 稳定性配置

| 选项 | 值 | 描述 |
|------|-----|------|
| circuit_breaker_enabled | true | 启用熔断器 |
| circuit_breaker_threshold | 5 | 熔断阈值 |
| retry_enabled | true | 启用重试 |
| retry_max_attempts | 3 | 最大重试次数 |
| retry_delay | 1000 | 重试延迟(毫秒) |

**spider_diary CLI 映射**:
```bash
spider-diary stability config --circuit-breaker --threshold 5 --retry --max-retry 3 --retry-delay 1000
```

### 5.4 告警阈值

| 指标 | 阈值 | 描述 |
|------|------|------|
| cpu_threshold | 80% | CPU使用率阈值 |
| memory_threshold | 85% | 内存使用率阈值 |
| disk_threshold | 90% | 磁盘使用率阈值 |
| error_rate_threshold | 5% | 错误率阈值 |

**spider_diary CLI 映射**:
```bash
spider-diary alert thresholds --cpu 80 --memory 85 --disk 90 --error-rate 5
```

---

## 6. 认证配置 (来自API文档.md)

| 选项 | 值 | 描述 |
|------|-----|------|
| auth.enabled | true | 启用认证 |
| jwt_secret | your-secret-key | JWT密钥 |
| jwt_expiration | 3600 | JWT过期时间(秒) |
| api_key_required | true | 需要API Key |

**spider_diary CLI 映射**:
```bash
spider-diary auth config --enabled --jwt-secret "your-secret-key" --jwt-expiration 3600 --api-key-required
```

---

**文档生成时间**: 2026-05-30
**文档版本**: v1.0
