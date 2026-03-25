# A-Stock Trading CLI — 智能对话式股票分析系统

基于 LLM Function Calling 的命令行交互式 A 股分析系统。通过自然语言对话，即可完成股票查询、技术分析、多 Agent 辩论、自选股管理等操作。

## 架构概览

```
用户终端 ←→ 对话主循环(chat.py) ←→ LLM (Function Calling)
                                         ↓
                                    工具执行层(cli_tools.py)
                                         ↓
                          ┌──────────────┼──────────────┐
                          ↓              ↓              ↓
                     数据抓取层     技术指标计算     AI辩论引擎
                  (data_fetchers)  (technical_ind)  (ai_service)
                          ↓              ↓              ↓
                          └──────────────┼──────────────┘
                                         ↓
                                    SQLite 数据库
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动对话

```bash
python chat.py
```

### 3. 首次配置 API Key

启动后，使用内置命令配置 AI 供应商：

```
/config set default_ai_provider deepseek
/config set deepseek_api_key sk-your-key-here
```

支持的 AI 供应商：`openai`、`deepseek`、`qwen`、`gemini`、`siliconflow`、`grok`

### 4. 开始对话

```
You > 查一下贵州茅台的实时行情
You > 分析一下600519的技术指标
You > 画一下茅台的日K线
You > 帮我深度分析一下000001
You > 加自选 600519
You > 帮我找找今天的强势股
You > 创建一个专注短线分析的Agent
```

## 功能列表

### 股票数据查询
- 实时行情（价格、涨跌幅、成交量、买卖盘口）
- K 线数据（日K、5分钟、15分钟、30分钟）
- 技术指标（MA、EMA、MACD、RSI、KDJ、BOLL、OBV）
- 资金流向（主力、超大单、大单、中单、小单净流入）
- 基本面数据（PE、PB、PS、市值、ROE、EPS）
- 行业板块信息与对比

### K 线图表
- 自动生成 K 线图（含均线和成交量）
- 保存为 PNG 文件并自动打开

### 多 Agent 辩论分析
- 多个 AI 分析师从不同角度分析股票
- 支持快速/均衡/深入三种分析模式
- 后台异步执行，完成后自动通知
- 生成综合投资分析报告

### 自选股管理
- 添加/删除/查看自选股

### 策略筛选
- 强势股筛选（涨停板）
- 低位启动股筛选（均线+MACD条件）

### Agent 管理
- 通过对话创建/修改/删除分析 Agent
- 自定义 Agent 提示词和角色
- 支持为不同 Agent 配置不同的 AI 供应商和模型

## 内置命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/config` | 查看当前 AI 配置 |
| `/config set <key> <value>` | 设置配置项 |
| `/agents` | 查看 Agent 列表 |
| `/clear` | 清除对话历史 |
| `/history` | 查看对话历史摘要 |
| `/quit` | 退出程序 |

## 文件结构

```
├── chat.py                 # CLI 对话入口（主程序）
├── cli_tools.py            # Function Calling 工具定义与执行
├── ai_service.py           # AI 服务调用（多供应商支持）
├── data_fetchers.py        # 股票数据抓取（东方财富/新浪）
├── data_formatters.py      # 数据格式化（供 AI 分析）
├── technical_indicators.py # 技术指标计算
├── models.py               # 数据库模型（SQLAlchemy + SQLite）
├── db.py                   # 数据库操作函数
├── init_agents.py          # 默认 Agent 初始化
├── utils.py                # 工具函数
└── requirements.txt        # Python 依赖
```

## 配置项参考

| 配置键 | 说明 | 示例值 |
|--------|------|--------|
| `default_ai_provider` | 默认 AI 供应商 | `deepseek` |
| `default_model` | 默认模型 | `deepseek-chat` |
| `openai_api_key` | OpenAI API Key | `sk-xxx` |
| `deepseek_api_key` | DeepSeek API Key | `sk-xxx` |
| `qwen_api_key` | 通义千问 API Key | `sk-xxx` |
| `gemini_api_key` | Gemini API Key | `AIza-xxx` |
| `siliconflow_api_key` | 硅基流动 API Key | `sk-xxx` |
| `grok_api_key` | Grok API Key | `xai-xxx` |

## 技术要点

**LLM Function Calling**：系统定义了 23 个工具函数，LLM 根据用户自然语言意图自主决定调用哪些工具获取数据，实现智能按需取数。

**多轮对话记忆**：维护完整的对话上下文，支持指代消解（如"它的资金流向怎么样"中的"它"指代上文提到的股票）。

**异步辩论**：辩论任务在后台线程执行，不阻塞对话。完成后通过回调机制在下次用户输入时通知。

**多供应商兼容**：支持 OpenAI 兼容格式的 Function Calling（OpenAI/DeepSeek/Qwen/SiliconFlow/Grok），以及 Gemini 的特殊适配。
