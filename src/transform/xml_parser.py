"""
XML Parser for Tool Calls
解析 content 中的 XML 格式工具调用 (兼容 Anthropic 手动工具调用格式)
"""
import re
import json
import uuid
from typing import Tuple, List, Dict, Any

def parse_xml_tool_calls(content: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    解析 content 中的 XML 格式工具调用
    返回: (cleaned_content, tool_calls_list)
    """
    # 检测 function_calls 块 (支持任意命名空间前缀如 antml:, atml: 等)
    xml_pattern = r'<(?:\w+:)?function_calls>(.*?)</(?:\w+:)?function_calls>'
    matches = re.search(xml_pattern, content, re.DOTALL)
    
    if not matches:
        return content, []
    
    xml_content = matches.group(1)
    tool_calls = []
    
    # 兼容任意命名空间前缀的 <invoke> 标签
    invoke_pattern = r'<(?:\w+:)?invoke name="(.*?)">(.*?)</(?:\w+:)?invoke>'
    invokes = re.findall(invoke_pattern, xml_content, re.DOTALL)
    
    for name, params_str in invokes:
        # 解析参数
        args = {}
        # 兼容任意命名空间前缀的 <parameter> 标签
        param_pattern = r'<(?:\w+:)?parameter name="(.*?)">(.*?)</(?:\w+:)?parameter>'

        params = re.findall(param_pattern, params_str, re.DOTALL)
        for param_name, param_value in params:
            # [修复] 参数名映射: 模型生成的 XML 可能使用错误的参数名
            # 例如 read_file: file_path -> path
            if name == "read_file" and param_name == "file_path":
                param_name = "path"
            
            args[param_name] = param_value.strip()
        
        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False)
            }
        })
            
    # 移除 XML 部分，只保留自然语言回复
    cleaned_content = re.sub(xml_pattern, "", content, flags=re.DOTALL).strip()
    
    return cleaned_content, tool_calls
