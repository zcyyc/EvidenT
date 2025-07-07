import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import logging
import time
import os

from tqdm import tqdm

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_trace_data(csv_path):
    """加载Trace数据"""
    start_time = time.time()
    logger.info(f"开始加载Trace数据: {csv_path}")
    
    # 加载数据
    df = pd.read_csv(csv_path)
    
    # 转换timestamp列
    if pd.api.types.is_integer_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    else:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    logger.info(f"Trace数据加载完成，共{len(df)}条记录，耗时: {(time.time() - start_time):.2f}秒")
    return df

def detect_trace_anomalies(df, group_cols=['trace_id'], 
                          time_col='timestamp', value_col='duration',
                          quantile_lower=0.05, quantile_upper=0.95,
                          window_days=7, min_data_points=20):
    """
    检测Trace数据中的异常
    
    参数:
    df: 输入DataFrame
    group_cols: 分组列，通常为[cmdb_id, trace_id]
    time_col: 时间戳列
    value_col: 要检测的数值列(duration)
    quantile_lower: 下分位数阈值
    quantile_upper: 上分位数阈值
    window_days: 滑动窗口天数
    min_data_points: 最小数据点阈值
    """
    start_time = time.time()
    logger.info(f"开始检测Trace异常，分组列: {group_cols}")
    
    all_anomalies = pd.DataFrame()
    
    # 获取所有唯一分组
    groups = df[group_cols].drop_duplicates()
    for i, group in tqdm(groups.iterrows(), desc="Processing groups", total=len(groups)):
        cmdb_id = group['cmdb_id']
        trace_id = group['trace_id'] if 'trace_id' in group_cols else None
        result = _detect_anomalies_for_group(
            df, cmdb_id, trace_id, group_cols, time_col, value_col,
            quantile_lower, quantile_upper
        )
        
        if result.empty:
            continue
        all_anomalies = pd.concat([all_anomalies, result], ignore_index=True)
    
    # with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
    #     tasks = []
    #     for i, group in tqdm(groups.iterrows(), desc="Processing groups", total=len(groups)):
    #         cmdb_id = group['cmdb_id']
    #         trace_id = group['trace_id'] if 'trace_id' in group_cols else None
            
    #         tasks.append(executor.submit(
    #             _detect_anomalies_for_group,
    #             df, cmdb_id, trace_id, group_cols, time_col, value_col,
    #             quantile_lower, quantile_upper, window_days, min_data_points
    #         ))
        
    #     # 处理完成的任务
    #     for i, future in enumerate(as_completed(tasks), 1):
    #         print(i)
    #         result = future.result()
    #         if not result.empty:
    #             all_anomalies.append(result)
            
    #         # 每处理100个分组输出进度
    #         if i % 100 == 0:
    #             logger.info(f"已完成 {i} 个分组的异常检测")
    
    logger.info(f"Trace异常检测完成，耗时: {(time.time() - start_time):.2f}秒，检测到 {len(all_anomalies)} 个异常")
    return all_anomalies

def _detect_anomalies_for_group(df, cmdb_id, trace_id, group_cols, time_col, value_col,
                               quantile_lower, quantile_upper):
    """处理单个分组的异常检测"""
    try:
        # 筛选当前分组数据
        if 'trace_id' in group_cols:
            group_data = df[(df['cmdb_id'] == cmdb_id) & (df['trace_id'] == trace_id)].copy()
        else:
            group_data = df[df['cmdb_id'] == cmdb_id].copy()
        
        if group_data.empty:
            return pd.DataFrame()
        
        # 按时间排序
        group_data = group_data.sort_values(time_col)
        
        # 检测异常
        mean_value = group_data[value_col].mean()
        std_value = group_data[value_col].std()
        threshold_multiplier = 3
        lower_threshold = mean_value - threshold_multiplier * std_value
        upper_threshold = mean_value + threshold_multiplier * std_value
        group_data['is_anomaly'] = (group_data[value_col] < lower_threshold) | (group_data[value_col] > upper_threshold)    
        
        # 处理持续异常 - 过滤短暂波动
        # group_data['anomaly_run'] = group_data['is_anomaly'].cumsum()
        # run_stats = group_data.groupby('anomaly_run')['is_anomaly'].sum()
        # valid_anomalies = run_stats[run_stats > 2].index  # 至少持续3个点的异常
        # group_data['is_significant_anomaly'] = group_data['anomaly_run'].isin(valid_anomalies)
        
        group_data['is_anomaly'] = group_data['is_anomaly'].astype(int)        
        if group_data['is_anomaly'].sum() == 0:
            return pd.DataFrame()
        
        # 提取异常记录
        anomalies = group_data[group_data['is_anomaly']==1].copy()
        anomalies['cmdb_id'] = cmdb_id
        if 'trace_id' in group_cols:
            anomalies['trace_id'] = trace_id
        logger.info(f"分组 cmdb_id={cmdb_id}, trace_id={trace_id} 的异常记录为{group_data['is_anomaly'].sum()}条")
        return anomalies[['timestamp', 'cmdb_id', 'trace_id' if 'trace_id' in group_cols else None, 
                          'duration', 'is_anomaly']]
    
    except Exception as e:
        logger.error(f"处理分组 cmdb_id={cmdb_id}, trace_id={trace_id} 时出错: {str(e)}")
        return pd.DataFrame()


def main(trace_df) -> pd.DataFrame:
    """主函数入口"""
    logger.info("开始Trace异常检测流程")
    
    trace_df = trace_df[trace_df['duration'] > 0]
    cmdb_visit_counts = trace_df['trace_id'].value_counts()
    # 只保留调用数量超过20的部分trace
    threshold = 20
    active_cmdb_ids = cmdb_visit_counts[cmdb_visit_counts >= threshold].index
    trace_df = trace_df[trace_df['trace_id'].isin(active_cmdb_ids)]
    
    # 检测异常
    trace_anomalies = detect_trace_anomalies(
        trace_df,
        group_cols=['cmdb_id', 'trace_id'],
        value_col='duration',
        quantile_lower=0.02,
        quantile_upper=0.98
    )
    
    # 保存结果
    if not trace_anomalies.empty:
        return trace_anomalies
    else:
        return {"message": "No anomalies detected."}