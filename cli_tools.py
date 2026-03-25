#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CLI 工具定义模块 —— 定义所有可供 LLM Function Calling 调用的工具
"""

import json
import os
import threading
import uuid
import time
import subprocess
import sys
import platform
from datetime import datetime

from models import SessionLocal
from db import (
    get_watchlist, add_to_watchlist, remove_from_watchlist,
    get_agents, get_agent, create_agent, update_agent, delete_agent,
    get_config, set_config, get_all_configs,
    create_debate_job, update_debate_job, get_debate_job, list_debate_jobs,
    cancel_debate_job, delete_debate_job,
)
from data_fetchers import (
    get_realtime_data, get_daily_kline, get_minute_kline,
    get_money_flow, get_money_flow_history, get_fundamental_data,
    get_sector_info, get_industry_comparison, get_timeline_data,
)
from technical_indicators import calculate_indicators, get_comprehensive_data_with_indicators
from data_formatters import format_for_ai
from ai_service import AIService
from utils import get_stock_code_format

# ==================== 工具 Schema 定义 ====================

TOOLS = [
    # ---------- 行情数据 ----------
    {
        "type": "function",
        "function": {
            "name": "get_stock_realtime",
            "description": "获取指定股票的实时行情数据，包括当前价格、涨跌幅、成交量、成交额、买卖盘口等",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码，如 600519、000001、300750"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_kline",
            "description": "获取股票K线数据，支持日K、5分钟K、15分钟K、30分钟K等多种周期",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    },
                    "kline_type": {
                        "type": "string",
                        "enum": ["daily", "minute5", "minute15", "minute30"],
                        "description": "K线类型：daily=日K线，minute5=5分钟，minute15=15分钟，minute30=30分钟"
                    },
                    "count": {
                        "type": "integer",
                        "description": "获取的K线数量，默认120",
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_technical_indicators",
            "description": "获取股票的技术指标分析，包括MA、EMA、MACD、RSI、KDJ、布林带、OBV等，并给出最新值和信号判断",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    # ---------- 资金流向 ----------
    {
        "type": "function",
        "function": {
            "name": "get_stock_money_flow",
            "description": "获取股票的资金流向数据，包括主力、超大单、大单、中单、小单的净流入流出",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    # ---------- 基本面 ----------
    {
        "type": "function",
        "function": {
            "name": "get_stock_fundamental",
            "description": "获取股票的基本面数据，包括PE、PB、PS、市值、ROE、EPS、营收、净利润等",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    # ---------- 行业信息 ----------
    {
        "type": "function",
        "function": {
            "name": "get_stock_sector_info",
            "description": "获取股票所属的板块和行业信息，以及行业内对比数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    # ---------- 综合数据（用于深度分析） ----------
    {
        "type": "function",
        "function": {
            "name": "get_stock_comprehensive",
            "description": "获取股票的全面综合数据（含实时行情、多周期K线、技术指标、资金流向、基本面、行业对比），适用于需要全面分析的场景",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    # ---------- K线图表 ----------
    {
        "type": "function",
        "function": {
            "name": "draw_kline_chart",
            "description": "绘制股票K线图并自动打开查看。支持日K线和分钟K线，包含均线和成交量",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    },
                    "kline_type": {
                        "type": "string",
                        "enum": ["daily", "minute5", "minute15", "minute30"],
                        "description": "K线类型，默认daily"
                    },
                    "count": {
                        "type": "integer",
                        "description": "K线数量，默认60"
                    }
                },
                "required": ["code"]
            }
        }
    },
    # ---------- 自选股管理 ----------
    {
        "type": "function",
        "function": {
            "name": "watchlist_list",
            "description": "查看当前自选股列表",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "watchlist_add",
            "description": "添加股票到自选股列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    },
                    "name": {
                        "type": "string",
                        "description": "股票名称（可选，不提供则自动获取）"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "watchlist_remove",
            "description": "从自选股列表中删除股票",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    }
                },
                "required": ["code"]
            }
        }
    },
    # ---------- 多Agent辩论 ----------
    {
        "type": "function",
        "function": {
            "name": "start_debate",
            "description": "启动多Agent辩论分析任务（后台异步执行）。多个AI Agent将从不同角度分析股票，然后进行辩论，最终生成综合报告",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "股票代码"
                    },
                    "agent_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "参与辩论的Agent ID列表，不提供则使用所有启用的Agent"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["fast", "balanced", "deep"],
                        "description": "分析模式：fast=快速(1轮分析1轮辩论)，balanced=均衡(2轮分析1轮辩论)，deep=深入(3轮分析2轮辩论)。默认balanced"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_debate_status",
            "description": "查看辩论任务的状态和进度",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "任务ID。不提供则显示所有任务列表"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_debate_report",
            "description": "获取已完成的辩论任务的最终分析报告",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["job_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_debate",
            "description": "终止正在运行的辩论任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "任务ID"
                    }
                },
                "required": ["job_id"]
            }
        }
    },
    # ---------- Agent管理 ----------
    {
        "type": "function",
        "function": {
            "name": "agent_list",
            "description": "查看所有Agent列表，包括名称、类型、是否启用、使用的AI供应商和模型",
            "parameters": {
                "type": "object",
                "properties": {
                    "enabled_only": {
                        "type": "boolean",
                        "description": "是否只显示启用的Agent，默认false"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_create",
            "description": "创建新的分析Agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Agent名称"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["default", "intraday_t", "review"],
                        "description": "Agent类型：default=综合分析，intraday_t=日内做T，review=复盘"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Agent的系统提示词，定义其分析角色和风格"
                    },
                    "ai_provider": {
                        "type": "string",
                        "enum": ["openai", "deepseek", "qwen", "gemini", "siliconflow", "grok"],
                        "description": "AI供应商（可选，不填则使用全局默认配置）"
                    },
                    "model": {
                        "type": "string",
                        "description": "模型名称（可选，不填则使用供应商默认模型）"
                    }
                },
                "required": ["name", "type", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_update",
            "description": "更新已有Agent的配置，如名称、提示词、启用状态、模型等",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "integer",
                        "description": "Agent ID"
                    },
                    "name": {"type": "string", "description": "新名称"},
                    "prompt": {"type": "string", "description": "新提示词"},
                    "enabled": {"type": "boolean", "description": "是否启用"},
                    "ai_provider": {"type": "string", "description": "AI供应商"},
                    "model": {"type": "string", "description": "模型名称"}
                },
                "required": ["agent_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "agent_delete",
            "description": "删除指定的Agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "integer",
                        "description": "Agent ID"
                    }
                },
                "required": ["agent_id"]
            }
        }
    },
    # ---------- 策略筛选 ----------
    {
        "type": "function",
        "function": {
            "name": "strategy_strong_stocks",
            "description": "筛选强势股（涨停或涨幅较大的股票）",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit_time": {
                        "type": "string",
                        "description": "涨停时间限制，如 10:00 表示10点前涨停的。默认不限制"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "strategy_low_start",
            "description": "筛选低位启动股（满足均线和MACD条件的潜力股）",
            "parameters": {
                "type": "object",
                "properties": {
                    "macd_type": {
                        "type": "string",
                        "enum": ["daily", "monthly"],
                        "description": "MACD类型：daily=日线MACD，monthly=月线MACD。默认daily"
                    }
                },
                "required": []
            }
        }
    },
    # ---------- 系统配置 ----------
    {
        "type": "function",
        "function": {
            "name": "config_get",
            "description": "查看系统配置，如AI供应商、API Key、默认模型等",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "配置键名。不提供则显示所有配置（API Key会脱敏显示）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "config_set",
            "description": "设置系统配置项，如AI供应商API Key、默认模型等",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "配置键名，如 openai_api_key, deepseek_api_key, default_ai_provider, default_model 等"
                    },
                    "value": {
                        "type": "string",
                        "description": "配置值"
                    }
                },
                "required": ["key", "value"]
            }
        }
    },
]


# ==================== 工具执行函数 ====================

def _safe_json(obj):
    """安全地将对象转为JSON字符串"""
    import pandas as pd
    if isinstance(obj, pd.DataFrame):
        if len(obj) > 30:
            # 只返回最近30条 + 统计摘要
            summary = {
                "total_rows": len(obj),
                "columns": list(obj.columns),
                "latest_30": json.loads(obj.tail(30).to_json(orient='records', date_format='iso')),
            }
            return json.dumps(summary, ensure_ascii=False, default=str)
        return obj.to_json(orient='records', date_format='iso', force_ascii=False)
    if obj is None:
        return json.dumps({"error": "未获取到数据"}, ensure_ascii=False)
    return json.dumps(obj, ensure_ascii=False, default=str)


def execute_tool(tool_name: str, arguments: dict, debate_callback=None) -> str:
    """
    执行指定的工具函数，返回结果字符串。
    debate_callback: 辩论完成时的回调函数
    """
    try:
        if tool_name == "get_stock_realtime":
            data = get_realtime_data(arguments["code"])
            return _safe_json(data)

        elif tool_name == "get_stock_kline":
            code = arguments["code"]
            kline_type = arguments.get("kline_type", "daily")
            count = arguments.get("count", 120)
            if kline_type == "daily":
                df = get_daily_kline(code, count=count)
            elif kline_type == "minute5":
                df = get_minute_kline(code, scale=5, datalen=count)
            elif kline_type == "minute15":
                df = get_minute_kline(code, scale=15, datalen=count)
            elif kline_type == "minute30":
                df = get_minute_kline(code, scale=30, datalen=count)
            else:
                df = get_daily_kline(code, count=count)
            return _safe_json(df)

        elif tool_name == "get_stock_technical_indicators":
            code = arguments["code"]
            df = get_daily_kline(code, count=240)
            if df is not None and len(df) > 0:
                df = calculate_indicators(df)
                latest = df.iloc[-1]
                indicators = {}
                # MA
                for col in [c for c in df.columns if c.startswith('MA') and not c.startswith('MACD')]:
                    if not _is_nan(latest.get(col)):
                        indicators[col] = round(float(latest[col]), 2)
                # EMA
                for col in [c for c in df.columns if c.startswith('EMA')]:
                    if not _is_nan(latest.get(col)):
                        indicators[col] = round(float(latest[col]), 2)
                # MACD
                if not _is_nan(latest.get('MACD_DIF')):
                    indicators['MACD_DIF'] = round(float(latest['MACD_DIF']), 3)
                    indicators['MACD_DEA'] = round(float(latest.get('MACD_DEA', 0)), 3)
                    indicators['MACD'] = round(float(latest.get('MACD', 0)), 3)
                    indicators['MACD_signal'] = '金叉' if latest['MACD_DIF'] > latest.get('MACD_DEA', 0) else '死叉'
                # RSI
                if not _is_nan(latest.get('RSI14')):
                    rsi = float(latest['RSI14'])
                    indicators['RSI14'] = round(rsi, 2)
                    indicators['RSI_status'] = '超买' if rsi > 70 else ('超卖' if rsi < 30 else '正常')
                # KDJ
                if not _is_nan(latest.get('KDJ_K')):
                    indicators['KDJ_K'] = round(float(latest['KDJ_K']), 2)
                    indicators['KDJ_D'] = round(float(latest.get('KDJ_D', 0)), 2)
                    indicators['KDJ_J'] = round(float(latest.get('KDJ_J', 0)), 2)
                    indicators['KDJ_signal'] = '金叉' if latest['KDJ_K'] > latest.get('KDJ_D', 0) else '死叉'
                # BOLL
                if not _is_nan(latest.get('BOLL_UPPER')):
                    indicators['BOLL_UPPER'] = round(float(latest['BOLL_UPPER']), 2)
                    indicators['BOLL_MID'] = round(float(latest.get('BOLL_MID', 0)), 2)
                    indicators['BOLL_LOWER'] = round(float(latest.get('BOLL_LOWER', 0)), 2)
                    price = float(latest.get('close', 0))
                    if price > float(latest['BOLL_UPPER']):
                        indicators['BOLL_position'] = '突破上轨'
                    elif price < float(latest.get('BOLL_LOWER', 0)):
                        indicators['BOLL_position'] = '跌破下轨'
                    else:
                        indicators['BOLL_position'] = '轨道内'
                # OBV
                if not _is_nan(latest.get('OBV')):
                    indicators['OBV'] = round(float(latest['OBV']), 0)

                return json.dumps({
                    "code": code,
                    "current_price": round(float(latest.get('close', 0)), 2),
                    "indicators": indicators
                }, ensure_ascii=False)
            return json.dumps({"error": "无法获取K线数据"}, ensure_ascii=False)

        elif tool_name == "get_stock_money_flow":
            data = get_money_flow(arguments["code"])
            return _safe_json(data)

        elif tool_name == "get_stock_fundamental":
            data = get_fundamental_data(arguments["code"])
            return _safe_json(data)

        elif tool_name == "get_stock_sector_info":
            code = arguments["code"]
            sector = get_sector_info(code)
            industry = get_industry_comparison(code, sector_info=sector)
            return json.dumps({
                "sectors": sector,
                "industry_comparison": industry
            }, ensure_ascii=False, default=str)

        elif tool_name == "get_stock_comprehensive":
            code = arguments["code"]
            data = get_comprehensive_data_with_indicators(code)
            formatted = format_for_ai(data)
            return formatted

        elif tool_name == "draw_kline_chart":
            return _draw_kline(arguments)

        elif tool_name == "watchlist_list":
            return _watchlist_list()

        elif tool_name == "watchlist_add":
            return _watchlist_add(arguments)

        elif tool_name == "watchlist_remove":
            return _watchlist_remove(arguments)

        elif tool_name == "start_debate":
            return _start_debate(arguments, debate_callback)

        elif tool_name == "check_debate_status":
            return _check_debate_status(arguments)

        elif tool_name == "get_debate_report":
            return _get_debate_report(arguments)

        elif tool_name == "stop_debate":
            return _stop_debate(arguments)

        elif tool_name == "agent_list":
            return _agent_list(arguments)

        elif tool_name == "agent_create":
            return _agent_create(arguments)

        elif tool_name == "agent_update":
            return _agent_update(arguments)

        elif tool_name == "agent_delete":
            return _agent_delete(arguments)

        elif tool_name == "strategy_strong_stocks":
            return _strategy_strong(arguments)

        elif tool_name == "strategy_low_start":
            return _strategy_low_start(arguments)

        elif tool_name == "config_get":
            return _config_get(arguments)

        elif tool_name == "config_set":
            return _config_set(arguments)

        else:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        import traceback
        return json.dumps({
            "error": f"工具执行失败: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False)


# ==================== 辅助函数 ====================

def _is_nan(val):
    """检查值是否为NaN"""
    import math
    if val is None:
        return True
    try:
        return math.isnan(float(val))
    except (TypeError, ValueError):
        return False


def _draw_kline(args):
    """绘制K线图"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.patches import Rectangle
        import numpy as np

        code = args["code"]
        kline_type = args.get("kline_type", "daily")
        count = args.get("count", 60)

        # 获取数据
        if kline_type == "daily":
            df = get_daily_kline(code, count=count)
            title_suffix = "日K线"
        elif kline_type == "minute5":
            df = get_minute_kline(code, scale=5, datalen=count)
            title_suffix = "5分钟K线"
        elif kline_type == "minute15":
            df = get_minute_kline(code, scale=15, datalen=count)
            title_suffix = "15分钟K线"
        elif kline_type == "minute30":
            df = get_minute_kline(code, scale=30, datalen=count)
            title_suffix = "30分钟K线"
        else:
            df = get_daily_kline(code, count=count)
            title_suffix = "日K线"

        if df is None or len(df) == 0:
            return json.dumps({"error": "无法获取K线数据"}, ensure_ascii=False)

        # 计算均线
        df = calculate_indicators(df, indicators=['MA'])

        # 获取股票名称
        rt = get_realtime_data(code)
        stock_name = rt.get('name', code) if rt else code

        # 绘图
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1],
                                        gridspec_kw={'hspace': 0.05})

        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False

        n = len(df)
        x = range(n)

        # 绘制K线
        for i in range(n):
            row = df.iloc[i]
            o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
            color = '#ef5350' if c >= o else '#26a69a'  # 红涨绿跌

            # 实体
            body_bottom = min(o, c)
            body_height = abs(c - o)
            rect = Rectangle((i - 0.35, body_bottom), 0.7, body_height if body_height > 0 else 0.01,
                              facecolor=color, edgecolor=color, linewidth=0.5)
            ax1.add_patch(rect)
            # 上下影线
            ax1.plot([i, i], [l, body_bottom], color=color, linewidth=0.8)
            ax1.plot([i, i], [min(o, c) + body_height, h], color=color, linewidth=0.8)

        # 均线
        ma_colors = {'MA5': '#FFD700', 'MA10': '#FF69B4', 'MA20': '#00BFFF', 'MA30': '#32CD32', 'MA60': '#FF4500'}
        for ma_name, ma_color in ma_colors.items():
            if ma_name in df.columns:
                vals = df[ma_name].values
                valid = ~np.isnan(vals.astype(float))
                ax1.plot(np.array(list(x))[valid], vals[valid], color=ma_color, linewidth=0.8, label=ma_name, alpha=0.8)

        ax1.set_xlim(-1, n)
        ax1.set_title(f'{stock_name}({code}) {title_suffix}', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.set_xticklabels([])

        # 成交量
        for i in range(n):
            row = df.iloc[i]
            o, c = float(row['open']), float(row['close'])
            vol = float(row.get('volume', 0))
            color = '#ef5350' if c >= o else '#26a69a'
            ax2.bar(i, vol, width=0.7, color=color, alpha=0.7)

        ax2.set_xlim(-1, n)
        ax2.set_ylabel('Volume', fontsize=10)
        ax2.grid(True, alpha=0.3)

        # X轴标签
        if kline_type == "daily" and 'date' in df.columns:
            tick_positions = list(range(0, n, max(1, n // 8)))
            tick_labels = [str(df.iloc[i]['date'])[:10] for i in tick_positions if i < n]
            ax2.set_xticks(tick_positions[:len(tick_labels)])
            ax2.set_xticklabels(tick_labels, rotation=45, fontsize=8)
        elif 'datetime' in df.columns:
            tick_positions = list(range(0, n, max(1, n // 8)))
            tick_labels = [str(df.iloc[i]['datetime'])[:16] for i in tick_positions if i < n]
            ax2.set_xticks(tick_positions[:len(tick_labels)])
            ax2.set_xticklabels(tick_labels, rotation=45, fontsize=8)

        plt.tight_layout()

        # 保存文件
        chart_dir = os.path.join(os.path.dirname(__file__), 'charts')
        os.makedirs(chart_dir, exist_ok=True)
        filename = f"{code}_{kline_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(chart_dir, filename)
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        # 尝试自动打开
        _open_file(filepath)

        return json.dumps({
            "success": True,
            "message": f"K线图已生成并保存到: {filepath}",
            "file": filepath
        }, ensure_ascii=False)

    except Exception as e:
        import traceback
        return json.dumps({"error": f"绘图失败: {str(e)}", "traceback": traceback.format_exc()}, ensure_ascii=False)


def _open_file(filepath):
    """跨平台打开文件"""
    try:
        system = platform.system()
        if system == 'Windows':
            os.startfile(filepath)
        elif system == 'Darwin':
            subprocess.Popen(['open', filepath])
        else:
            subprocess.Popen(['xdg-open', filepath])
    except Exception:
        pass  # 静默失败，用户可以手动打开


def _watchlist_list():
    """查看自选股"""
    db = SessionLocal()
    try:
        items = get_watchlist(db)
        result = []
        for item in items:
            result.append({
                "code": item.code,
                "name": item.name or "",
                "added_at": str(item.added_at) if item.added_at else "",
                "sort_order": item.sort_order
            })
        return json.dumps({"watchlist": result, "total": len(result)}, ensure_ascii=False)
    finally:
        db.close()


def _watchlist_add(args):
    """添加自选股"""
    db = SessionLocal()
    try:
        code = args["code"]
        name = args.get("name")
        if not name:
            rt = get_realtime_data(code)
            name = rt.get('name', '') if rt else ''
        item = add_to_watchlist(db, code, name)
        return json.dumps({
            "success": True,
            "message": f"已添加 {name}({code}) 到自选股"
        }, ensure_ascii=False)
    finally:
        db.close()


def _watchlist_remove(args):
    """删除自选股"""
    db = SessionLocal()
    try:
        code = args["code"]
        ok = remove_from_watchlist(db, code)
        if ok:
            return json.dumps({"success": True, "message": f"已从自选股中移除 {code}"}, ensure_ascii=False)
        else:
            return json.dumps({"success": False, "message": f"自选股中未找到 {code}"}, ensure_ascii=False)
    finally:
        db.close()


def _start_debate(args, callback=None):
    """启动辩论任务"""
    db = SessionLocal()
    try:
        code = args["code"]
        mode = args.get("mode", "balanced")
        mode_map = {
            "fast": (1, 1),
            "balanced": (2, 1),
            "deep": (3, 2),
        }
        analysis_rounds, debate_rounds = mode_map.get(mode, (2, 1))

        # 获取Agent列表
        agent_ids = args.get("agent_ids")
        if not agent_ids:
            agents = get_agents(db, enabled_only=True)
            agent_ids = [a.id for a in agents]

        if len(agent_ids) < 2:
            return json.dumps({"error": "至少需要2个Agent参与辩论"}, ensure_ascii=False)

        # 获取股票名称
        rt = get_realtime_data(code)
        stock_name = rt.get('name', code) if rt else code

        # 创建任务
        job_id = str(uuid.uuid4())[:12]
        name = f"{stock_name}({code}) {mode}模式分析"
        create_debate_job(db, job_id, code, name, agent_ids, analysis_rounds, debate_rounds,
                         meta={"mode": mode})

        # 后台线程执行
        t = threading.Thread(
            target=_run_debate_worker,
            args=(job_id, code, agent_ids, analysis_rounds, debate_rounds, callback),
            daemon=True
        )
        t.start()

        return json.dumps({
            "success": True,
            "job_id": job_id,
            "message": f"辩论任务已启动（{mode}模式），任务ID: {job_id}。可使用 check_debate_status 查看进度。"
        }, ensure_ascii=False)
    finally:
        db.close()


def _run_debate_worker(job_id, code, agent_ids, analysis_rounds, debate_rounds, callback=None):
    """辩论任务后台工作线程"""
    db = SessionLocal()
    try:
        # 更新状态为运行中
        update_debate_job(db, job_id, status='running', progress=5)

        # 获取综合数据
        data = get_comprehensive_data_with_indicators(code)
        formatted_data = format_for_ai(data)
        update_debate_job(db, job_id, progress=10)

        # 获取Agent配置
        agents = []
        for aid in agent_ids:
            agent = get_agent(db, aid)
            if agent:
                agents.append(agent)

        if len(agents) < 2:
            update_debate_job(db, job_id, status='failed', error='可用Agent不足2个')
            return

        # 获取AI配置
        configs = get_all_configs(db)
        default_provider = configs.get('default_ai_provider', 'openai')
        default_model_map = {
            'openai': 'gpt-4o',
            'deepseek': 'deepseek-chat',
            'qwen': 'qwen-plus',
            'gemini': 'gemini-pro',
            'siliconflow': 'Qwen/Qwen2.5-72B-Instruct',
            'grok': 'grok-4-0709',
        }

        def resolve_config(agent):
            provider = agent.ai_provider or default_provider
            model = agent.model or default_model_map.get(provider, 'gpt-4o')
            api_key = configs.get(f'{provider}_api_key', '')
            return provider, model, api_key

        steps = []
        total_steps = len(agents) * analysis_rounds + len(agents) * debate_rounds + 1
        current_step = 0

        # ===== 分析阶段 =====
        analysis_results = {}
        for round_num in range(1, analysis_rounds + 1):
            for agent in agents:
                # 检查取消
                job = get_debate_job(db, job_id)
                if job and job.canceled:
                    update_debate_job(db, job_id, status='canceled')
                    return

                provider, model, api_key = resolve_config(agent)
                if not api_key:
                    steps.append({
                        "phase": "analysis", "round": round_num,
                        "agent_id": agent.id, "agent_name": agent.name,
                        "content": f"[错误] 未配置 {provider} 的API Key",
                        "timestamp": datetime.now().isoformat()
                    })
                    continue

                # 构建prompt
                prev_analysis = analysis_results.get(agent.id, "")
                prompt = f"""{agent.prompt}

以下是股票数据：
{formatted_data}

{"以下是你上一轮的分析，请在此基础上深化和补充：" + chr(10) + prev_analysis if prev_analysis else ""}

请给出你的第{round_num}轮分析。"""

                try:
                    result = AIService.call_agent(provider, api_key, model, prompt)
                    analysis_results[agent.id] = result
                    steps.append({
                        "phase": "analysis", "round": round_num,
                        "agent_id": agent.id, "agent_name": agent.name,
                        "content": result,
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception as e:
                    steps.append({
                        "phase": "analysis", "round": round_num,
                        "agent_id": agent.id, "agent_name": agent.name,
                        "content": f"[错误] AI调用失败: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    })

                current_step += 1
                progress = 10 + int(current_step / total_steps * 80)
                update_debate_job(db, job_id, progress=progress,
                                 steps=json.dumps(steps, ensure_ascii=False))

        # ===== 辩论阶段 =====
        for round_num in range(1, debate_rounds + 1):
            for agent in agents:
                job = get_debate_job(db, job_id)
                if job and job.canceled:
                    update_debate_job(db, job_id, status='canceled')
                    return

                provider, model, api_key = resolve_config(agent)
                if not api_key:
                    continue

                # 收集其他Agent的观点
                other_views = []
                for other in agents:
                    if other.id != agent.id and other.id in analysis_results:
                        other_views.append(f"【{other.name}的观点】\n{analysis_results[other.id]}")

                prompt = f"""{agent.prompt}

以下是股票数据：
{formatted_data}

以下是你之前的分析：
{analysis_results.get(agent.id, '暂无')}

以下是其他分析师的观点：
{chr(10).join(other_views)}

这是第{round_num}轮辩论。请针对其他分析师的观点进行回应，坚持你认为正确的判断，指出你不同意的地方并给出理由。"""

                try:
                    result = AIService.call_agent(provider, api_key, model, prompt)
                    analysis_results[agent.id] = result
                    steps.append({
                        "phase": "debate", "round": round_num,
                        "agent_id": agent.id, "agent_name": agent.name,
                        "content": result,
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception as e:
                    steps.append({
                        "phase": "debate", "round": round_num,
                        "agent_id": agent.id, "agent_name": agent.name,
                        "content": f"[错误] AI调用失败: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    })

                current_step += 1
                progress = 10 + int(current_step / total_steps * 80)
                update_debate_job(db, job_id, progress=progress,
                                 steps=json.dumps(steps, ensure_ascii=False))

        # ===== 生成最终报告 =====
        update_debate_job(db, job_id, progress=92)

        # 使用第一个Agent的配置来生成报告
        reporter = agents[0]
        provider, model, api_key = resolve_config(reporter)

        all_views = []
        for agent in agents:
            if agent.id in analysis_results:
                all_views.append(f"## {agent.name}\n{analysis_results[agent.id]}")

        report_prompt = f"""你是一位资深的投资分析总监。以下是多位分析师对股票的分析和辩论结果。
请综合所有观点，生成一份全面的投资分析报告。

报告要求：
1. 用Markdown格式输出
2. 包含：综合评级、核心观点、技术面分析、基本面分析、资金面分析、风险提示、操作建议
3. 对于分析师之间的分歧，给出你的判断
4. 最后给出明确的投资建议（买入/持有/卖出）和目标价位

各分析师观点：
{chr(10).join(all_views)}
"""

        try:
            report = AIService.call_agent(provider, api_key, model, report_prompt)
        except Exception as e:
            report = f"# 报告生成失败\n\n错误: {str(e)}\n\n## 各Agent分析摘要\n\n" + "\n\n".join(all_views)

        update_debate_job(db, job_id,
                         status='completed',
                         progress=100,
                         steps=json.dumps(steps, ensure_ascii=False),
                         report_md=report)

        # 回调通知
        if callback:
            callback(job_id, code, "completed")

    except Exception as e:
        import traceback
        update_debate_job(db, job_id, status='failed', error=str(e))
        if callback:
            callback(job_id, code, "failed")
    finally:
        db.close()


def _check_debate_status(args):
    """查看辩论状态"""
    db = SessionLocal()
    try:
        job_id = args.get("job_id")
        if job_id:
            job = get_debate_job(db, job_id)
            if not job:
                return json.dumps({"error": f"未找到任务 {job_id}"}, ensure_ascii=False)
            return json.dumps({
                "job_id": job.job_id,
                "code": job.code,
                "name": job.name,
                "status": job.status,
                "progress": job.progress,
                "error": job.error,
                "created_at": str(job.created_at),
                "updated_at": str(job.updated_at),
            }, ensure_ascii=False)
        else:
            jobs = list_debate_jobs(db, limit=20)
            result = []
            for job in jobs:
                result.append({
                    "job_id": job.job_id,
                    "code": job.code,
                    "name": job.name,
                    "status": job.status,
                    "progress": job.progress,
                    "created_at": str(job.created_at),
                })
            return json.dumps({"jobs": result, "total": len(result)}, ensure_ascii=False)
    finally:
        db.close()


def _get_debate_report(args):
    """获取辩论报告"""
    db = SessionLocal()
    try:
        job_id = args["job_id"]
        job = get_debate_job(db, job_id)
        if not job:
            return json.dumps({"error": f"未找到任务 {job_id}"}, ensure_ascii=False)
        if job.status != 'completed':
            return json.dumps({
                "error": f"任务尚未完成，当前状态: {job.status}，进度: {job.progress}%"
            }, ensure_ascii=False)
        return json.dumps({
            "job_id": job.job_id,
            "name": job.name,
            "report": job.report_md,
        }, ensure_ascii=False)
    finally:
        db.close()


def _stop_debate(args):
    """终止辩论"""
    db = SessionLocal()
    try:
        job_id = args["job_id"]
        job = cancel_debate_job(db, job_id)
        if job:
            return json.dumps({"success": True, "message": f"已请求终止任务 {job_id}"}, ensure_ascii=False)
        return json.dumps({"error": f"未找到任务 {job_id}"}, ensure_ascii=False)
    finally:
        db.close()


def _agent_list(args):
    """Agent列表"""
    db = SessionLocal()
    try:
        enabled_only = args.get("enabled_only", False)
        agents = get_agents(db, enabled_only=enabled_only)
        result = []
        for a in agents:
            result.append({
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "enabled": a.enabled,
                "ai_provider": a.ai_provider or "(全局默认)",
                "model": a.model or "(全局默认)",
                "prompt_preview": (a.prompt or "")[:80] + "..." if a.prompt and len(a.prompt) > 80 else (a.prompt or ""),
            })
        return json.dumps({"agents": result, "total": len(result)}, ensure_ascii=False)
    finally:
        db.close()


def _agent_create(args):
    """创建Agent"""
    db = SessionLocal()
    try:
        agent = create_agent(
            db,
            name=args["name"],
            type=args["type"],
            prompt=args["prompt"],
            ai_provider=args.get("ai_provider"),
            model=args.get("model"),
            enabled=True,
        )
        return json.dumps({
            "success": True,
            "agent_id": agent.id,
            "message": f"Agent '{agent.name}' 创建成功，ID: {agent.id}"
        }, ensure_ascii=False)
    finally:
        db.close()


def _agent_update(args):
    """更新Agent"""
    db = SessionLocal()
    try:
        agent_id = args.pop("agent_id")
        # 过滤掉None值
        updates = {k: v for k, v in args.items() if v is not None}
        agent = update_agent(db, agent_id, **updates)
        if agent:
            return json.dumps({
                "success": True,
                "message": f"Agent '{agent.name}' (ID:{agent.id}) 更新成功"
            }, ensure_ascii=False)
        return json.dumps({"error": f"未找到Agent ID: {agent_id}"}, ensure_ascii=False)
    finally:
        db.close()


def _agent_delete(args):
    """删除Agent"""
    db = SessionLocal()
    try:
        agent_id = args["agent_id"]
        ok = delete_agent(db, agent_id)
        if ok:
            return json.dumps({"success": True, "message": f"Agent ID:{agent_id} 已删除"}, ensure_ascii=False)
        return json.dumps({"error": f"未找到Agent ID: {agent_id}"}, ensure_ascii=False)
    finally:
        db.close()


def _strategy_strong(args):
    """强势股筛选"""
    try:
        import akshare as ak
        limit_time = args.get("limit_time", "")
        df = ak.stock_zt_pool_em(date=datetime.now().strftime('%Y%m%d'))
        if df is not None and len(df) > 0:
            if limit_time:
                df = df[df['首次封板时间'] <= limit_time] if '首次封板时间' in df.columns else df
            records = []
            for _, row in df.head(30).iterrows():
                records.append({
                    "代码": str(row.get('代码', '')),
                    "名称": str(row.get('名称', '')),
                    "涨跌幅": str(row.get('涨跌幅', '')),
                    "最新价": str(row.get('最新价', '')),
                    "封板时间": str(row.get('首次封板时间', '')),
                    "连板数": str(row.get('连板数', '')),
                })
            return json.dumps({"strong_stocks": records, "total": len(df)}, ensure_ascii=False)
        return json.dumps({"strong_stocks": [], "message": "未获取到数据"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"筛选失败: {str(e)}"}, ensure_ascii=False)


def _strategy_low_start(args):
    """低位启动股筛选"""
    try:
        from technical_indicators import check_low_start_strategy
        import akshare as ak
        macd_type = args.get("macd_type", "daily")

        # 获取A股列表
        df_list = ak.stock_zh_a_spot_em()
        if df_list is None or len(df_list) == 0:
            return json.dumps({"error": "无法获取股票列表"}, ensure_ascii=False)

        results = []
        checked = 0
        for _, row in df_list.iterrows():
            code = str(row.get('代码', ''))
            if not code or code.startswith(('68', '4', '8', '9')):
                continue
            checked += 1
            if checked > 200:  # 限制检查数量
                break
            try:
                kline = get_daily_kline(code, count=500)
                if kline is not None and len(kline) >= 200:
                    result = check_low_start_strategy(kline, macd_type=macd_type)
                    if result.get('passed'):
                        name = str(row.get('名称', ''))
                        price = str(row.get('最新价', ''))
                        results.append({
                            "代码": code,
                            "名称": name,
                            "最新价": price,
                            "原因": result.get('reason', ''),
                        })
                time.sleep(0.05)
            except Exception:
                continue

        return json.dumps({
            "low_start_stocks": results,
            "total": len(results),
            "checked": checked,
            "macd_type": macd_type
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"筛选失败: {str(e)}"}, ensure_ascii=False)


def _config_get(args):
    """获取配置"""
    db = SessionLocal()
    try:
        key = args.get("key")
        if key:
            val = get_config(db, key)
            # API Key脱敏
            if 'api_key' in key.lower() and val:
                val = val[:8] + '****' + val[-4:] if len(val) > 12 else '****'
            return json.dumps({"key": key, "value": val}, ensure_ascii=False)
        else:
            configs = get_all_configs(db)
            # 脱敏
            safe_configs = {}
            for k, v in configs.items():
                if 'api_key' in k.lower() and v:
                    safe_configs[k] = v[:8] + '****' + v[-4:] if len(v) > 12 else '****'
                else:
                    safe_configs[k] = v
            return json.dumps({"configs": safe_configs}, ensure_ascii=False)
    finally:
        db.close()


def _config_set(args):
    """设置配置"""
    db = SessionLocal()
    try:
        key = args["key"]
        value = args["value"]
        set_config(db, key, value)
        # 显示时脱敏
        display_val = value
        if 'api_key' in key.lower():
            display_val = value[:8] + '****' + value[-4:] if len(value) > 12 else '****'
        return json.dumps({
            "success": True,
            "message": f"配置 {key} 已设置为 {display_val}"
        }, ensure_ascii=False)
    finally:
        db.close()
