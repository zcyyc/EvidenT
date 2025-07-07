from zoneinfo import ZoneInfo
import numpy
import pandas as pd
import time
from typing import Dict, Union, Optional, List
import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def detect_timestamp_format(sample_value: Union[str, int, float]) -> Optional[str]:
    """
    自动检测时间戳格式
    
    Args:
        sample_value: 时间戳样本值
    
    Returns:
        str: 时间格式描述 ('datetime', 'unix_seconds', 'unix_milliseconds')
             或 None (无法识别)
    """
    print("sample_value:", sample_value)
    print("type(sample_value):", type(sample_value))
    if isinstance(sample_value, str):
        try:
            # 尝试解析为datetime字符串
            pd.to_datetime(sample_value)
            return 'datetime'
        except:
            return None
    
    elif isinstance(sample_value, numpy.integer):
        value = int(sample_value)
        
        # 根据数值范围判断时间戳单位
        if value > 1e12:  # 毫秒级时间戳
            return 'unix_milliseconds'
        elif value > 1e8:  # 秒级时间戳
            return 'unix_seconds'
        else:
            return None
    
    return None

def split_data(data: Dict[str, Union[str, Union[str, pd.Timestamp]]]) -> pd.DataFrame:
    """
    基于时间范围分割数据
    
    Args:
        data (dict): 包含以下键的字典
            - data_path (str): 数据文件路径
            - start_timestamp (str|pd.Timestamp): 开始时间戳
            - end_timestamp (str|pd.Timestamp): 结束时间戳
    
    Returns:
        pd.DataFrame: 筛选后的DataFrame
    """
    # 参数校验
    required_keys = {'data_path', 'start_timestamp', 'end_timestamp'}
    missing_keys = required_keys - set(data.keys())
    if missing_keys:
        raise ValueError(f"缺少必要的参数: {', '.join(missing_keys)}")
    
    data_path = data['data_path']
    start_timestamp = data['start_timestamp']
    end_timestamp = data['end_timestamp']
    
    # 文件检查
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"数据文件不存在: {data_path}")
    
    # 读取数据
    try:
        df = pd.read_csv(data_path)
    except Exception as e:
        raise RuntimeError(f"读取文件失败: {data_path}, 错误: {str(e)}")
    
    # 检查时间戳列是否存在
    if 'timestamp' not in df.columns:
        raise ValueError(f"DataFrame中不存在时间戳列: 'timestamp'")
    
    # 获取样本值用于格式检测
    sample_value = df['timestamp'].iloc[0]
    
    # 检测时间戳格式
    timestamp_format = detect_timestamp_format(sample_value)
    print("timestamp_format:", timestamp_format)
    logger.info(f"检测到时间戳格式: {timestamp_format}")
    
    # 转换时间戳列
    try:
        if timestamp_format == 'datetime':
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        elif timestamp_format == 'unix_seconds':
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')  # 设置为UTC时区
            df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Shanghai')
            df['timestamp'] = df['timestamp'].dt.tz_localize(None)  # 移除时区信息
            
        elif timestamp_format == 'unix_milliseconds':
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')  # 设置为UTC时区
            df['timestamp'] = df['timestamp'].dt.tz_convert('Asia/Shanghai')
            df['timestamp'] = df['timestamp'].dt.tz_localize(None)
        else:
            raise ValueError(f"无法识别时间戳格式: {sample_value}")
    except Exception as e:
        raise ValueError(f"时间戳转换失败: {str(e)}")
 
    logger.info(f"时间戳已转换为: {df['timestamp'].dtype}")
    
    # 转换查询时间
    try:
        if not isinstance(start_timestamp, pd.Timestamp):
            start_timestamp = pd.to_datetime(start_timestamp)
        if not isinstance(end_timestamp, pd.Timestamp):
            end_timestamp = pd.to_datetime(end_timestamp)
    except Exception as e:
        raise ValueError(f"查询时间转换失败: {str(e)}")
    
    # 时间范围筛选
    filtered_df = df[(df['timestamp'] >= start_timestamp) & (df['timestamp'] <= end_timestamp)]
    
    # 记录筛选统计信息
    original_count = len(df)
    filtered_count = len(filtered_df)
    logger.info(f"数据筛选完成: {data_path}")
    logger.info(f"原始记录数: {original_count}, 筛选后记录数: {filtered_count}")
    logger.info(f"时间范围: {start_timestamp} 至 {end_timestamp}")
    logger.info(f"筛选比例: {filtered_count/original_count:.2%}")
    
    return filtered_df

def batch_split_data(data_configs: List[Dict[str, Union[str, Union[str, pd.Timestamp]]]], 
                     output_dir: Optional[str] = None,
                     default_prefix: str = "split_data") -> None:
    """
    批量处理多个数据分割任务
    
    Args:
        data_configs (List[Dict]): 数据配置列表，每个配置是一个字典
        output_dir (str, optional): 输出目录，默认为None（使用输入文件所在目录）
        default_prefix (str, optional): 默认输出文件前缀
    """
    for i, config in enumerate(data_configs):
        logger.info(f"\n正在处理第 {i+1}/{len(data_configs)} 个任务...")
        try:
            # 执行数据分割
            result_df = split_data(config)
            
            # 确定输出路径
            input_path = config['data_path']
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                file_name = os.path.basename(input_path)
                output_path = os.path.join(output_dir, file_name)
            else:
                dir_name = os.path.dirname(input_path)
                base_name = os.path.basename(input_path)
                file_name, ext = os.path.splitext(base_name)
                output_path = os.path.join(dir_name, f"{default_prefix}_{file_name}{ext}")
            
            # 保存结果
            result_df.to_csv(output_path, index=False)
            logger.info(f"结果已保存至: {output_path}")
            
        except Exception as e:
            logger.error(f"处理任务失败: {str(e)}")
            continue

if __name__ == "__main__":
    # 定义时间范围
    start_time = '2021-03-04 14:40:00'
    end_time = '2021-03-04 15:10:00'
    
    # 配置数据处理任务
    data_configs = [
        {
            'data_path': r'D:\PythonCode\aiops_mcp\utils\all_anomalies.csv',
            'start_timestamp': start_time,
            'end_timestamp': end_time,
        },
        {
            'data_path': r'D:\PythonCode\aiops_mcp\Bank\telemetry\2021_03_04\log\log_service.csv',
            'start_timestamp': start_time,
            'end_timestamp': end_time,
        },
        {
            'data_path': r'D:\PythonCode\aiops_mcp\Bank\telemetry\2021_03_04\trace\trace_span.csv',
            'start_timestamp': start_time,
            'end_timestamp': end_time,
        }
    ]
    
    # 执行批量处理
    batch_split_data(data_configs)
    
    logger.info("\n所有任务处理完成！")    