#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""技术指标计算模块"""

import pandas as pd
import numpy as np
import warnings
import time
from datetime import datetime
from data_fetchers import get_daily_kline, get_timeline_data, get_minute_kline, get_realtime_data, get_sector_info, get_money_flow, get_fundamental_data, get_industry_comparison
warnings.filterwarnings("ignore")

def calculate_ma(df, periods=[5, 10, 20, 30, 60]):
    """计算移动平均线（MA）"""
    if df is None or len(df) == 0 or 'close' not in df.columns:
        return df
    df = df.copy()
    for period in periods:
        df[f'MA{period}'] = df['close'].rolling(window=period, min_periods=1).mean()
    return df


def calculate_ema(df, periods=[12, 26, 50]):
    """计算指数移动平均线（EMA）"""
    if df is None or len(df) == 0 or 'close' not in df.columns:
        return df
    df = df.copy()
    for period in periods:
        df[f'EMA{period}'] = df['close'].ewm(span=period, adjust=False).mean()
    return df


def calculate_macd(df, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    if df is None or len(df) == 0 or 'close' not in df.columns:
        return df
    df = df.copy()
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    df['MACD_DIF'] = ema_fast - ema_slow
    df['MACD_DEA'] = df['MACD_DIF'].ewm(span=signal, adjust=False).mean()
    df['MACD'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2
    return df


def calculate_rsi(df, period=14):
    """计算RSI相对强弱指标"""
    if df is None or len(df) == 0 or 'close' not in df.columns:
        return df
    df = df.copy()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()
    rs = gain / loss
    df[f'RSI{period}'] = 100 - (100 / (1 + rs))
    return df


def calculate_kdj(df, n=9, m1=3, m2=3):
    """计算KDJ指标"""
    if df is None or len(df) == 0:
        return df
    if 'high' not in df.columns or 'low' not in df.columns or 'close' not in df.columns:
        return df
    df = df.copy()
    low_list = df['low'].rolling(window=n, min_periods=1).min()
    high_list = df['high'].rolling(window=n, min_periods=1).max()
    rsv = (df['close'] - low_list) / (high_list - low_list) * 100
    df['KDJ_K'] = rsv.ewm(com=m1-1, adjust=False).mean()
    df['KDJ_D'] = df['KDJ_K'].ewm(com=m2-1, adjust=False).mean()
    df['KDJ_J'] = 3 * df['KDJ_K'] - 2 * df['KDJ_D']
    return df


def calculate_boll(df, period=20, std_dev=2):
    """计算布林带（BOLL）"""
    if df is None or len(df) == 0 or 'close' not in df.columns:
        return df
    df = df.copy()
    df['BOLL_MID'] = df['close'].rolling(window=period, min_periods=1).mean()
    std = df['close'].rolling(window=period, min_periods=1).std()
    df['BOLL_UPPER'] = df['BOLL_MID'] + (std * std_dev)
    df['BOLL_LOWER'] = df['BOLL_MID'] - (std * std_dev)
    return df


def calculate_obv(df):
    """计算OBV能量潮指标"""
    if df is None or len(df) == 0:
        return df
    if 'close' not in df.columns or 'volume' not in df.columns:
        return df
    df = df.copy()
    price_change = df['close'].diff()
    obv = (np.sign(price_change) * df['volume']).fillna(0)
    df['OBV'] = obv.cumsum()
    return df


def check_low_start_strategy(df, macd_type='daily'):
    """检测低位启动股策略
    条件：
    1. 股价 >= MA200 (10月线)
    2. 股价 >= MA50 (10周线)
    3. 股价 >= MA600 (10季线)
    4. 股价 <= MA200 * 1.2
    5. MA200 > MA400 (10月线上穿20月线，金叉状态)
    6. MACD DIF > DEA (MACD金叉状态)

    Args:
        df: K线数据DataFrame
        macd_type: 'daily' 日MACD 或 'monthly' 月MACD

    Returns:
        dict: {'passed': bool, 'reason': str}
    """
    # 根据MACD类型检查最小数据要求
    min_periods = 600 if macd_type == 'daily' else 60  # 月MACD需要至少60个月数据
    min_period_name = '600天' if macd_type == 'daily' else '60个月'

    if df is None or len(df) < min_periods:
        return {'passed': False, 'reason': f'数据不足{min_period_name}'}

    current_price = df['close'].iloc[-1]

    # 计算所需均线（日K线的MA200=10月线，月K线的MA10=10月线）
    if macd_type == 'daily':
        ma200 = df['close'].rolling(window=200, min_periods=1).mean().iloc[-1]
        ma400 = df['close'].rolling(window=400, min_periods=1).mean().iloc[-1]
        ma50 = df['close'].rolling(window=50, min_periods=1).mean().iloc[-1]
        ma600 = df['close'].rolling(window=600, min_periods=1).mean().iloc[-1]
        ma_label = '日MA'
    else:
        # 月K线：10个月≈10月线，20个月≈20月线
        ma10 = df['close'].rolling(window=10, min_periods=1).mean().iloc[-1]   # 10月线
        ma20 = df['close'].rolling(window=20, min_periods=1).mean().iloc[-1]   # 20月线
        # 为了兼容返回格式，映射到对应字段
        ma200 = ma10  # 10月线
        ma400 = ma20  # 20月线
        # 10周线（约2.5月）和10季线在月K线下无法准确计算，使用近似值
        ma50 = ma10   # 近似10周线
        ma600 = df['close'].rolling(window=30, min_periods=1).mean().iloc[-1]  # 30季线≈10季线
        ma_label = '月MA'

    # 计算MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()

    latest_dif = dif.iloc[-1]
    latest_dea = dea.iloc[-1]

    # 检查条件
    if pd.isna(ma200) or pd.isna(ma400) or pd.isna(ma50) or pd.isna(ma600):
        return {'passed': False, 'reason': '均线数据不完整'}

    # 条件1: 股价 >= 10月线
    if current_price < ma200:
        return {'passed': False, 'reason': f'股价{current_price:.2f} < 10月线{ma200:.2f}'}

    # 条件2: 股价 >= 10周线
    if current_price < ma50:
        return {'passed': False, 'reason': f'股价{current_price:.2f} < 10周线{ma50:.2f}'}

    # 条件3: 股价 >= 10季线
    if current_price < ma600:
        return {'passed': False, 'reason': f'股价{current_price:.2f} < 10季线{ma600:.2f}'}

    # 条件4: 股价 <= 10月线 * 1.2
    if current_price > ma200 * 1.2:
        return {'passed': False, 'reason': f'股价{current_price:.2f} > 10月线*1.2 ({ma200*1.2:.2f})'}

    # 条件5: 10月线上穿20月线 (金叉状态)
    if ma200 <= ma400:
        return {'passed': False, 'reason': f'10月线({ma200:.2f}) 未上穿20月线({ma400:.2f})'}

    # 条件6: MACD金叉
    macd_label = '月MACD' if macd_type == 'monthly' else '日MACD'
    if pd.isna(latest_dif) or pd.isna(latest_dea) or latest_dif <= latest_dea:
        return {'passed': False, 'reason': f'{macd_label}未金叉 (DIF={latest_dif:.3f}, DEA={latest_dea:.3f})'}

    return {
        'passed': True,
        'reason': f'符合条件 ({macd_label}金叉)',
        'ma200': ma200,
        'ma400': ma400,
        'ma50': ma50,
        'ma600': ma600,
        'macd_dif': latest_dif,
        'macd_dea': latest_dea,
        'macd_type': macd_type
    }

    return {
        'passed': True,
        'reason': '符合条件',
        'ma200': ma200,
        'ma400': ma400,
        'ma50': ma50,
        'ma600': ma600,
        'macd_dif': latest_dif,
        'macd_dea': latest_dea
    }


def calculate_indicators(df, indicators=['MA', 'EMA', 'MACD', 'RSI', 'KDJ', 'BOLL', 'OBV']):
    """批量计算技术指标"""
    if df is None or len(df) == 0:
        return df
    result_df = df.copy()
    if 'MA' in indicators:
        result_df = calculate_ma(result_df, periods=[5, 10, 20, 30, 60])
    if 'EMA' in indicators:
        result_df = calculate_ema(result_df, periods=[12, 26, 50])
    if 'MACD' in indicators:
        result_df = calculate_macd(result_df)
    if 'RSI' in indicators:
        result_df = calculate_rsi(result_df, period=14)
    if 'KDJ' in indicators:
        result_df = calculate_kdj(result_df)
    if 'BOLL' in indicators:
        result_df = calculate_boll(result_df)
    if 'OBV' in indicators:
        result_df = calculate_obv(result_df)
    return result_df


# ==================== 数据整合函数 ====================

def get_comprehensive_data(code):
    """获取股票的综合数据"""
    result = {
        'code': code,
        'timestamp': datetime.now().isoformat(),
        'realtime': None,
        'minute_5': None,
        'minute_15': None,
        'minute_30': None,
        'timeline': None,
        'daily': None,
        'sector_info': None,  # 板块/行业信息
        'money_flow': None,   # 资金流向
        'fundamental': None,  # 基本面数据
        'industry_comparison': None,  # 行业对比数据
    }
    
    print(f"[API] 获取 {code} 实时行情...")
    result['realtime'] = get_realtime_data(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 5分钟K线...")
    result['minute_5'] = get_minute_kline(code, scale=5, datalen=240)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 15分钟K线...")
    result['minute_15'] = get_minute_kline(code, scale=15, datalen=160)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 30分钟K线...")
    result['minute_30'] = get_minute_kline(code, scale=30, datalen=80)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 分时数据...")
    result['timeline'] = get_timeline_data(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 日K线...")
    result['daily'] = get_daily_kline(code, count=240)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 板块/行业信息...")
    result['sector_info'] = get_sector_info(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 资金流向...")
    result['money_flow'] = get_money_flow(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 基本面数据...")
    result['fundamental'] = get_fundamental_data(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 行业对比数据...")
    result['industry_comparison'] = get_industry_comparison(code, sector_info=result.get('sector_info'))
    
    # 计算换手率：换手率 = (成交量 / 流通股本) * 100%
    # 成交量单位：股（新浪API的fields[8]返回的是股数，不是手数）
    # 流通股本单位：亿股
    if result['realtime'] and result['fundamental']:
        volume = result['realtime'].get('volume')  # 成交量（股）
        circulating_shares = result['fundamental'].get('circulating_shares')  # 流通股本（亿股）
        
        if volume and circulating_shares and circulating_shares > 0:
            # 换手率 = 成交量（股） / (流通股本亿股 * 100000000股/亿股) * 100%
            # = volume / (circulating_shares * 100000000) * 100
            turnover_rate = volume / (circulating_shares * 100000000) * 100
            result['realtime']['turnover_rate'] = turnover_rate
            print(f"[API] 计算换手率: {turnover_rate:.2f}% (成交量={volume}股, 流通股本={circulating_shares}亿股)")
    
    return result


def get_comprehensive_data_with_indicators(code):
    """获取股票的综合数据（包含技术指标）"""
    result = {
        'code': code,
        'timestamp': datetime.now().isoformat(),
        'realtime': None,
        'minute_5': None,
        'minute_15': None,
        'minute_30': None,
        'timeline': None,
        'daily': None,
        'indicators': None,  # 技术指标摘要
        'sector_info': None,  # 板块/行业信息
        'money_flow': None,   # 资金流向
        'fundamental': None,  # 基本面数据
        'industry_comparison': None,  # 行业对比数据
    }
    
    print(f"[API] 获取 {code} 实时行情...")
    result['realtime'] = get_realtime_data(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 5分钟K线...")
    result['minute_5'] = get_minute_kline(code, scale=5, datalen=240)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 15分钟K线...")
    result['minute_15'] = get_minute_kline(code, scale=15, datalen=160)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 30分钟K线...")
    result['minute_30'] = get_minute_kline(code, scale=30, datalen=80)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 分时数据...")
    result['timeline'] = get_timeline_data(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 日K线...")
    daily_df = get_daily_kline(code, count=240)
    if daily_df is not None and len(daily_df) > 0:
        print(f"[API] 计算 {code} 技术指标...")
        daily_df = calculate_indicators(daily_df)
        result['daily'] = daily_df
        
        # 提取最新技术指标摘要
        if len(daily_df) > 0:
            latest = daily_df.iloc[-1]
            indicators_summary = {}
            
            ma_cols = [col for col in daily_df.columns if col.startswith('MA') and not col.startswith('MACD')]
            if ma_cols:
                indicators_summary['MA'] = {col: float(latest[col]) for col in ma_cols if pd.notna(latest[col])}
            
            ema_cols = [col for col in daily_df.columns if col.startswith('EMA')]
            if ema_cols:
                indicators_summary['EMA'] = {col: float(latest[col]) for col in ema_cols if pd.notna(latest[col])}
            
            if 'MACD_DIF' in daily_df.columns and pd.notna(latest['MACD_DIF']):
                indicators_summary['MACD'] = {
                    'DIF': float(latest['MACD_DIF']),
                    'DEA': float(latest.get('MACD_DEA', 0)) if pd.notna(latest.get('MACD_DEA')) else 0,
                    'MACD': float(latest.get('MACD', 0)) if pd.notna(latest.get('MACD')) else 0
                }
            
            if 'RSI14' in daily_df.columns and pd.notna(latest['RSI14']):
                indicators_summary['RSI'] = float(latest['RSI14'])
            
            if 'KDJ_K' in daily_df.columns and pd.notna(latest['KDJ_K']):
                indicators_summary['KDJ'] = {
                    'K': float(latest['KDJ_K']),
                    'D': float(latest.get('KDJ_D', 0)) if pd.notna(latest.get('KDJ_D')) else 0,
                    'J': float(latest.get('KDJ_J', 0)) if pd.notna(latest.get('KDJ_J')) else 0
                }
            
            if 'BOLL_UPPER' in daily_df.columns and pd.notna(latest['BOLL_UPPER']):
                indicators_summary['BOLL'] = {
                    'upper': float(latest['BOLL_UPPER']),
                    'mid': float(latest.get('BOLL_MID', 0)) if pd.notna(latest.get('BOLL_MID')) else 0,
                    'lower': float(latest.get('BOLL_LOWER', 0)) if pd.notna(latest.get('BOLL_LOWER')) else 0
                }
            
            if 'OBV' in daily_df.columns and pd.notna(latest['OBV']):
                indicators_summary['OBV'] = float(latest['OBV'])
            
            result['indicators'] = indicators_summary
    else:
        result['daily'] = None
    
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 板块/行业信息...")
    result['sector_info'] = get_sector_info(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 资金流向...")
    result['money_flow'] = get_money_flow(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 基本面数据...")
    result['fundamental'] = get_fundamental_data(code)
    time.sleep(0.1)
    
    print(f"[API] 获取 {code} 行业对比数据...")
    result['industry_comparison'] = get_industry_comparison(code, sector_info=result.get('sector_info'))
    
    # 计算换手率：换手率 = (成交量 / 流通股本) * 100%
    # 成交量单位：股（新浪API的fields[8]返回的是股数，不是手数）
    # 流通股本单位：亿股
    if result['realtime'] and result['fundamental']:
        volume = result['realtime'].get('volume')  # 成交量（股）
        circulating_shares = result['fundamental'].get('circulating_shares')  # 流通股本（亿股）
        
        if volume and circulating_shares and circulating_shares > 0:
            # 换手率 = 成交量（股） / (流通股本亿股 * 100000000股/亿股) * 100%
            # = volume / (circulating_shares * 100000000) * 100
            turnover_rate = volume / (circulating_shares * 100000000) * 100
            result['realtime']['turnover_rate'] = turnover_rate
            print(f"[API] 计算换手率: {turnover_rate:.2f}% (成交量={volume}股, 流通股本={circulating_shares}亿股)")
    
    return result