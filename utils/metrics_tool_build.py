import os
import shutil
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_data(app_csv_path, container_csv_path):
    """加载两个数据源的数据"""
    start_time = time.time()
    logger.info(f"开始加载数据: {app_csv_path} 和 {container_csv_path}")
    
    # 加载metrics_app.csv
    df_app = pd.read_csv(app_csv_path)
    
    # 转换timestamp列
    if pd.api.types.is_integer_dtype(df_app['timestamp']):
        df_app['timestamp'] = pd.to_datetime(df_app['timestamp'], unit='s')
    else:
        df_app['timestamp'] = pd.to_datetime(df_app['timestamp'])
    
    # 加载metrics_container.csv
    df_container = pd.read_csv(container_csv_path)
    
    # 转换timestamp列
    if pd.api.types.is_integer_dtype(df_container['timestamp']):
        df_container['timestamp'] = pd.to_datetime(df_container['timestamp'], unit='s')
    else:
        df_container['timestamp'] = pd.to_datetime(df_container['timestamp'])
    
    # 从kpi_name中提取有意义的指标名称
    df_container['metric'] = df_container['kpi_name'].apply(lambda x: x.split('-')[-1].strip())
    
    logger.info(f"数据加载完成，耗时: {(time.time() - start_time):.2f}秒")
    return df_app, df_container

def detect_anomalies_component_metric(args):
    """处理单个组件和指标的异常检测"""
    df, component, metric, data_type = args
    
    try:
        if data_type == 'app':
            # 处理app数据
            component_data = df[df['tc'] == component].copy()
            if component_data.empty or metric not in component_data.columns:
                return pd.DataFrame()
                
            # 数据预处理
            if metric == 'sr':  # 成功率指标特殊处理
                component_data[metric] = component_data[metric].clip(0, 100)
            elif metric == 'rr':  # 响应率指标特殊处理
                component_data[metric] = component_data[metric].clip(0, 100)
            
            # 准备数据
            df_processed = component_data.rename(columns={
                'timestamp': 'ds',
                metric: 'y'})[['ds', 'y']].dropna()
        else:
            # 处理container数据
            component_data = df[(df['cmdb_id'] == component) & (df['metric'] == metric)].copy()
            if component_data.empty:
                return pd.DataFrame()
                
            # 准备数据
            df_processed = component_data.rename(columns={
                'timestamp': 'ds',
                'value': 'y'
            })[['ds', 'y']].dropna()
        
        if len(df_processed) < 10:  # 数据点太少，跳过
            return pd.DataFrame()
            
        # 确保数据按时间排序
        if not df_processed['ds'].is_monotonic_increasing:
            df_processed = df_processed.sort_values('ds')
        
        # 检查是否所有值都相同
        data_std = df_processed['y'].std()
        if data_std < 1e-6:  # 考虑浮点数精度问题
            return pd.DataFrame()
            
        # 使用3-sigma方法进行异常检测
        window_size = min(20, len(df_processed) // 2)  # 动态窗口大小
        
        # 计算移动均值和标准差
        df_processed['yhat'] = df_processed['y'].rolling(window=window_size, min_periods=1).mean()
        df_processed['y_std'] = df_processed['y'].rolling(window=window_size, min_periods=1).std()
        
        # 处理标准差为零的情况
        df_processed['y_std'] = df_processed['y_std'].apply(lambda x: max(x, 1e-6))  # 避免除零错误
        
        # 计算3-sigma上下界
        sigma_threshold = 3.0  # 可调整的阈值
        df_processed['yhat_lower'] = df_processed['yhat'] - sigma_threshold * df_processed['y_std']
        df_processed['yhat_upper'] = df_processed['yhat'] + sigma_threshold * df_processed['y_std']
        
        # 检测异常
        df_processed['is_anomaly'] = (df_processed['y'] < df_processed['yhat_lower']) | (df_processed['y'] > df_processed['yhat_upper'])
        
        if data_type == 'app':
            df_processed['tc'] = component
            df_processed['metric_name'] = metric
        else:
            df_processed['tc'] = component
            df_processed['metric_name'] = metric
        
        return df_processed[df_processed['is_anomaly']]
    
    except Exception as e:
        logger.error(f"处理组件 {component} 的 {metric} 指标时出错: {str(e)}")
        return pd.DataFrame()

def detect_anomalies_parallel(df, component_col, metric_col, value_col, timestamp_col='timestamp', data_type='app'):
    """使用并行处理进行异常检测"""
    start_time = time.time()
    logger.info(f"开始并行检测 {data_type} 数据，组件列: {component_col}, 指标列: {metric_col}")
    
    # 获取所有唯一组件和指标
    components = df[component_col].unique()
    metrics = df[metric_col].unique() if metric_col else [None]
    
    all_anomalies = []
    
    # 准备并行任务参数
    tasks = []
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        for component in components:
            for metric in metrics:
                tasks.append(executor.submit(
                    detect_anomalies_component_metric, 
                    (df, component, metric, data_type)
                ))
        
        # 处理完成的任务
        for i, future in enumerate(as_completed(tasks), 1):
            result = future.result()
            if not result.empty:
                all_anomalies.append(result)
            
            # 每处理100个任务输出进度
            if i % 100 == 0:
                logger.info(f"已完成 {i} 个任务")
    
    logger.info(f"并行检测完成，耗时: {(time.time() - start_time):.2f}秒，检测到 {len(all_anomalies)} 个异常块")
    return pd.concat(all_anomalies, ignore_index=True) if all_anomalies else pd.DataFrame()

def format_results(all_anomalies, source_type):
    """将结果格式化为[timestamp, metric_name, value]"""
    if all_anomalies.empty:
        return pd.DataFrame(columns=['timestamp', 'metric_name', 'value', 'tc', 'source'])
    
    # 筛选异常记录并按要求格式输出
    formatted_results = all_anomalies.rename(columns={
        'ds': 'timestamp',
        'y': 'value'
    })[['timestamp', 'metric_name', 'value', 'tc']]
    
    # 添加数据源标识
    formatted_results['source'] = source_type
    
    return formatted_results

# 使用示例
if __name__ == "__main__":
    start_time = time.time()
    logger.info("开始异常检测流程")
    
    # 加载数据
    csv1_path = r'D:\PythonCode\aiops_mcp\Bank\telemetry\2021_03_04\metric\metric_app.csv'
    csv2_path = r'D:\PythonCode\aiops_mcp\Bank\telemetry\2021_03_04\metric\metric_container.csv'
    df_app, df_container = load_data(csv1_path, csv2_path)
    
    # 并行检测app数据
    app_anomalies = detect_anomalies_parallel(
        df=df_app,
        component_col='tc',
        metric_col=None,  # app数据的指标在列中
        value_col='rr',  # 注意：这里需要调整，实际应循环处理多个指标
        data_type='app'
    )
    
    # 并行检测container数据
    container_anomalies = detect_anomalies_parallel(
        df=df_container,
        component_col='cmdb_id',
        metric_col='metric',
        value_col='value',
        data_type='container'
    )
    
    # 格式化结果
    formatted_app_anomalies = format_results(app_anomalies, 'app')
    formatted_container_anomalies = format_results(container_anomalies, 'container')
    
    # 合并结果
    all_formatted_anomalies = pd.concat([
        formatted_app_anomalies,
        formatted_container_anomalies
    ], ignore_index=True)
    
    # 保存结果
    if not all_formatted_anomalies.empty:
        all_formatted_anomalies.to_csv('all_anomalies.csv', index=False)
        logger.info(f"已检测到 {len(all_formatted_anomalies)} 个异常，结果已保存")
    else:
        logger.info("未检测到异常或数据不足")
    
    logger.info(f"整个流程完成，总耗时: {(time.time() - start_time):.2f}秒")