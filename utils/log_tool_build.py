import re
import pandas as pd
import numpy as np
from typing import List, Dict, Any

# 日志类型配置字典，可扩展支持更多日志类型
LOG_TYPES = {
    'localhost_access_log': {
        'pattern': r'^IG\d+ POST (.*?) HTTP/1.1 200 (\d+) - k6/0.29.0 \(api_url (\d+) (\d+\.\d+)',
        'fields': ['url', 'response_size', 'response_time', 'api_flag']
    },
    'apache_access_log': {
        'pattern': r'^IPAddress "POST (.*?) HTTP/1.1" 200 (\d+) "-" "k6/0.29.0 \(api_url (\d+) (\d)',
        'fields': ['url', 'response_size', 'response_time', 'status_flag']
    },
    'gc': {
        'pattern': r'^(\d+\.\d+): .*?real=(\d+\.\d+) secs\]$',
        'fields': ['timestamp', 'real_time'],
        'additional_pattern': r'user=(\d+\.\d+) sys=(\d+\.\d+),',
        'additional_fields': ['user_time', 'sys_time']
    }
}

def parse_log_line(log_text: str, log_type: str) -> Dict[str, Any]:
    """根据日志类型解析日志文本并返回结构化数据"""
    if log_type not in LOG_TYPES:
        return None
    
    config = LOG_TYPES[log_type]
    match = re.search(config['pattern'], log_text)
    if not match:
        return None
    
    data = {'type': log_type}
    for i, field in enumerate(config['fields']):
        # 自动转换数值类型
        try:
            data[field] = int(match.group(i+1))
        except ValueError:
            try:
                data[field] = float(match.group(i+1))
            except ValueError:
                data[field] = match.group(i+1)
    
    # 处理GC日志的额外字段
    if log_type == 'gc' and 'additional_pattern' in config:
        add_match = re.search(config['additional_pattern'], log_text)
        if add_match:
            for i, field in enumerate(config['additional_fields']):
                data[field] = float(add_match.group(i+1))
    return data

def detect_access_log_anomalies(access_records: List[Dict[str, Any]], threshold_std: float = 10.0) -> List[Dict[str, Any]]:
    """检测访问日志中的异常（响应时间、大小及状态标志）"""
    if not access_records:
        return []
    
    anomalies = []
    # 按日志类型分组处理
    type_records = {'apache': [], 'localhost': []}
    for record in access_records:
        if record['type'] == 'apache_access_log':
            type_records['apache'].append(record)
        elif record['type'] == 'localhost_access_log':
            type_records['localhost'].append(record)
    
    # 处理Localhost访问日志
    if type_records['localhost']:
        df = pd.DataFrame(type_records['localhost'])
        for url, group in df.groupby('url'):
            # 响应时间异常检测
            mean_time = group['response_time'].mean()
            std_time = group['response_time'].std()
            time_anomalies = group[(group['response_time'] > mean_time + threshold_std * std_time) |
                                  (group['response_time'] < mean_time - threshold_std * std_time)]
            # 响应大小异常检测
            mean_size = group['response_size'].mean()
            std_size = group['response_size'].std()
            size_anomalies = group[(group['response_size'] > mean_size + threshold_std * std_size) |
                                  (group['response_size'] < mean_size - threshold_std * std_size)]
            
            # 收集异常
            for _, record in time_anomalies.iterrows():
                anomalies.append({
                    'type': 'localhost_access_log',
                    'anomaly_type': 'response_time',
                    'url': record['url'],
                    'response_time': record['response_time'],
                    'expected_range': f"[{mean_time - threshold_std * std_time:.0f}, {mean_time + threshold_std * std_time:.0f}]",
                    'api_flag': record['api_flag'],
                    'cmdb_id': record.get('cmdb_id', 'N/A'),
                    'detect_time': record.get('detect_time', 'N/A')
                })
            for _, record in size_anomalies.iterrows():
                anomalies.append({
                    'type': 'localhost_access_log',
                    'anomaly_type': 'response_size',
                    'url': record['url'],
                    'response_size': record['response_size'],
                    'expected_range': f"[{mean_size - threshold_std * std_size:.0f}, {mean_size + threshold_std * std_size:.0f}]",
                    'api_flag': record['api_flag'],
                    'cmdb_id': record.get('cmdb_id', 'N/A'),
                    'detect_time': record.get('detect_time', 'N/A')
                })
            
    # 处理Apache访问日志（示例中未提供，保留扩展接口）
    if type_records['apache']:
        df = pd.DataFrame(type_records['apache'])
        for url, group in df.groupby('url'):
            # 响应时间异常检测
            mean_time = group['response_time'].mean()
            std_time = group['response_time'].std()
            time_anomalies = group[(group['response_time'] > mean_time + threshold_std * std_time) |
                                  (group['response_time'] < mean_time - threshold_std * std_time)]
            # 响应大小异常检测
            mean_size = group['response_size'].mean()
            std_size = group['response_size'].std()
            size_anomalies = group[(group['response_size'] > mean_size + threshold_std * std_size) |
                                  (group['response_size'] < mean_size - threshold_std * std_size)]
            
            # 收集异常
            for _, record in time_anomalies.iterrows():
                anomalies.append({
                    'type': 'apache_access_log',
                    'anomaly_type': 'response_time',
                    'url': record['url'],
                    'response_time': record['response_time'],
                    'expected_range': f"[{mean_time - threshold_std * std_time:.0f}, {mean_time + threshold_std * std_time:.0f}]",
                    'status_flag': record['status_flag'],
                    'cmdb_id': record.get('cmdb_id', 'N/A'),
                    'detect_time': record.get('detect_time', 'N/A')
                })
            for _, record in size_anomalies.iterrows():
                anomalies.append({
                    'type': 'apache_access_log',
                    'anomaly_type': 'response_size',
                    'url': record['url'],
                    'response_size': record['response_size'],
                    'expected_range': f"[{mean_size - threshold_std * std_size:.0f}, {mean_size + threshold_std * std_size:.0f}]",
                    'status_flag': record['status_flag'],
                    'cmdb_id': record.get('cmdb_id', 'N/A'),
                    'detect_time': record.get('detect_time', 'N/A')
                })
    
    return anomalies

def detect_anomalies(log_data: pd.DataFrame, threshold_std: float = 3.0) -> List[Dict[str, Any]]:
    """
    检测多种类型日志中的异常
    :param log_data: 包含日志数据的DataFrame，需包含log_name、value、cmdb_id列
    :param threshold_std: 标准差倍数阈值
    :return: 异常列表
    """
    parsed_records = []
    for _, row in log_data.iterrows():
        log_detect_time = row.get('timestamp', None)
        log_text = row.get('value', '')
        log_type = row.get('log_name', '')
        cmdb_id = row.get('cmdb_id', 'N/A')
        
        parsed = parse_log_line(log_text, log_type)
        if parsed:
            parsed['cmdb_id'] = cmdb_id  # 添加CMDB ID
            parsed['detect_time'] = log_detect_time  # 添加时间戳
            parsed_records.append(parsed)
    
    if not parsed_records:
        return []
    
    # 分离访问日志（示例中主要处理localhost_access_log）
    access_records = [r for r in parsed_records if r['type'] in ['apache_access_log', 'localhost_access_log']]
    
    # 检测访问日志异常
    anomalies = detect_access_log_anomalies(access_records, threshold_std)
    
    return anomalies


# if __name__ == "__main__":
#     log_df = pd.read_csv(r'D:\PythonCode\aiops_mcp\Bank\telemetry\2021_03_04\log\split_data_log_service.csv')
#     print(log_df.shape)
#     # 检测异常（设置2倍标准差为阈值，提高敏感度）
#     anomalies = detect_anomalies(log_df, threshold_std=3.0)
#     print(len(anomalies))
#     df = pd.DataFrame(anomalies)