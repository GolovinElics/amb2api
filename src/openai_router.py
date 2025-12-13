"""
OpenAI Router - Handles OpenAI format API requests
处理OpenAI格式请求的路由模块
"""
import json
import time
import uuid
import asyncio
import re
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import get_available_models_async, is_fake_streaming_model, is_anti_truncation_model, get_base_model_from_feature_model, get_anti_truncation_max_attempts
from log import log
from .anti_truncation import apply_anti_truncation_to_stream
from .assembly_client import send_assembly_request
from .models import ChatCompletionRequest, ModelList, Model
from .task_manager import create_managed_task
from .openai_transfer import assembly_response_to_openai

def _parse_xml_tool_calls(content: str):
    """
    解析 content 中的 XML 格式工具调用 (兼容 Anthropic 手动工具调用格式)
    支持两种格式:
    1. <function_calls><invoke name="...">...</invoke></function_calls>
    2. <function_calls><invoke name="...">...</invoke></function_calls>
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


# 创建路由器
router = APIRouter()
security = HTTPBearer()

# AssemblyAI 适配不需要 Google 凭证管理器

async def authenticate(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """验证用户密码"""
    from config import get_api_password
    password = await get_api_password()
    token = credentials.credentials
    if token != password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    return token

@router.get("/v1/models", response_model=ModelList)
async def list_models():
    """返回OpenAI格式的模型列表"""
    models = await get_available_models_async("openai")
    return ModelList(data=[Model(id=m) for m in models])

@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    token: str = Depends(authenticate)
):
    """处理OpenAI格式的聊天完成请求"""
    
    # 获取原始请求数据
    try:
        raw_data = await request.json()
        # 记录请求中的所有参数（排除 messages 内容以减少日志量）
        params_to_log = {k: v for k, v in raw_data.items() if k != 'messages'}
        log.info(f"Request params: model={raw_data.get('model')}, stream={raw_data.get('stream')}, extra_keys={list(params_to_log.keys())}")
        log.debug(f"Full request params (excluding messages): {json.dumps(params_to_log, ensure_ascii=False)[:500]}...")
    except Exception as e:
        log.error(f"Failed to parse JSON request: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    
    # 创建请求对象
    try:
        request_data = ChatCompletionRequest(**raw_data)
        log.debug(f"Request validated - model: {request_data.model}, messages: {len(request_data.messages)}, stream: {getattr(request_data, 'stream', False)}")
        
        # 详细记录接收到的消息结构
        log.debug(f"Received messages structure:")
        for i, m in enumerate(request_data.messages):
            role = getattr(m, "role", "unknown")
            has_tool_calls = bool(getattr(m, "tool_calls", None))
            has_tool_call_id = bool(getattr(m, "tool_call_id", None))
            content_preview = str(getattr(m, "content", ""))[:50]
            log.debug(f"  [{i}] role={role}, tool_calls={has_tool_calls}, tool_call_id={has_tool_call_id}, content={content_preview}...")
    except Exception as e:
        log.error(f"Request validation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Request validation error: {str(e)}")
    
    # 健康检查
    if (len(request_data.messages) == 1 and 
        getattr(request_data.messages[0], "role", None) == "user" and
        getattr(request_data.messages[0], "content", None) == "Hi"):
        return JSONResponse(content={
            "choices": [{"message": {"role": "assistant", "content": "amb2api正常工作中"}}]
        })
    
    # 限制max_tokens
    if getattr(request_data, "max_tokens", None) is not None and request_data.max_tokens > 65535:
        request_data.max_tokens = 65535
    
    # Max Tokens 自适应处理
    try:
        from src.storage_adapter import get_storage_adapter
        from .model_limits import get_model_max_tokens
        
        adapter = await get_storage_adapter()
        max_tokens_mode = await adapter.get_config("max_tokens_mode", "off")
        
        if max_tokens_mode != "off":
            model_max = await get_model_max_tokens(request_data.model)
            
            if max_tokens_mode == "high":
                target_max_tokens = model_max
            elif max_tokens_mode == "medium":
                target_max_tokens = model_max // 2
            else:  # low
                target_max_tokens = min(4096, model_max)
            
            original_max_tokens = getattr(request_data, "max_tokens", None)
            request_data.max_tokens = target_max_tokens
            log.info(f"Max tokens adaptive: mode={max_tokens_mode}, model_max={model_max}, original={original_max_tokens}, target={target_max_tokens}")
    except Exception as e:
        log.warning(f"Max tokens adaptive processing failed: {e}")
        
    # 覆写 top_k 为 64
    setattr(request_data, "top_k", 64)

    # 过滤空消息（但保留有 tool_calls 的消息和 assistant/tool 消息）
    filtered_messages = []
    for m in request_data.messages:
        content = getattr(m, "content", None)
        tool_calls = getattr(m, "tool_calls", None)
        role = getattr(m, "role", "unknown")
        
        # 如果有 tool_calls，即使 content 为空也保留
        if tool_calls:
            log.debug(f"Keeping message with tool_calls: role={role}, content={'[empty]' if not content else content[:50]+'...'}")
            filtered_messages.append(m)
            continue
        
        # 保留 assistant 和 tool 消息，即使 content 为空
        # 这对于多轮对话很重要
        if role in ["assistant", "tool"]:
            filtered_messages.append(m)
            continue
        
        # 对于其他角色，检查 content 是否有效
        if content:
            if isinstance(content, str) and content.strip():
                filtered_messages.append(m)
            elif isinstance(content, list) and len(content) > 0:
                has_valid_content = False
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text" and part.get("text", "").strip():
                            has_valid_content = True
                            break
                        elif part.get("type") == "image_url" and part.get("image_url", {}).get("url"):
                            has_valid_content = True
                            break
                if has_valid_content:
                    filtered_messages.append(m)
    
    request_data.messages = filtered_messages
    
    log.debug(f"After filtering: {len(request_data.messages)} messages")
    for i, m in enumerate(request_data.messages):
        role = getattr(m, "role", "unknown")
        has_tool_calls = bool(getattr(m, "tool_calls", None))
        content_preview = str(getattr(m, "content", ""))[:50]
        log.debug(f"  [{i}] role={role}, has_tool_calls={has_tool_calls}, content={content_preview}...")
    
    # AssemblyAI 支持完整的 OpenAI 协议，不需要重建消息
    
    # 优化消息历史，避免超出 token 限制
    from .message_optimizer import optimize_messages
    try:
        optimized_messages = optimize_messages(request_data.messages)
        request_data.messages = optimized_messages
        log.debug(f"Messages optimized: {len(filtered_messages)} -> {len(optimized_messages)}")
    except Exception as e:
        log.warning(f"Message optimization failed: {e}, using original messages")
    
    # 处理模型名称和功能检测
    model = request_data.model
    use_fake_streaming = is_fake_streaming_model(model)
    use_anti_truncation = is_anti_truncation_model(model)
    
    # AssemblyAI 直接使用传入模型名，无需特征前缀转换
    
    # 处理假流式
    if use_fake_streaming and getattr(request_data, "stream", False):
        request_data.stream = False
        return await fake_stream_response_for_assembly(request_data)
    
    # 处理抗截断 (仅流式传输时有效)
    is_streaming = getattr(request_data, "stream", False)
    if use_anti_truncation and is_streaming:
        log.warning("AssemblyAI 暂不支持原生流式抗截断，将作为普通请求处理")
        request_data.stream = False
        is_streaming = False
    
    # 发送到 AssemblyAI（非流式）
    is_streaming = getattr(request_data, "stream", False)
    if is_streaming:
        # 检查是否启用真实流式
        from config import get_enable_real_streaming
        enable_real_streaming = await get_enable_real_streaming()
        
        if enable_real_streaming:
            log.info("使用真实流式模式（实验性）")
            # 真实流式模式：直接发送流式请求到 AssemblyAI
            # 注意：当前 AssemblyAI 的流式响应可能存在解析问题
            response = await send_assembly_request(request_data, True)
            return await convert_streaming_response(response, model)
        else:
            log.info("使用假流式模式")
            return await fake_stream_response_for_assembly(request_data)
    
    log.info(f"REQ model={model}")
    log.debug(f"Sending request to AssemblyAI - stream: {is_streaming}, messages: {len(request_data.messages)}")
    
    response = await send_assembly_request(request_data, False)
    
    # 如果是流式响应，直接返回
    if is_streaming:
        log.debug(f"Converting to streaming response for model: {model}")
        return await convert_streaming_response(response, model)
    
    # 转换非流式响应（AssemblyAI → OpenAI）
    try:
        try:
            if hasattr(response, 'text') and isinstance(getattr(response, 'text'), str):
                text = response.text
            elif hasattr(response, 'body'):
                body = response.body
                text = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else str(body)
            elif hasattr(response, 'content'):
                content = response.content
                text = content.decode('utf-8', errors='replace') if isinstance(content, bytes) else str(content)
            else:
                text = str(response)
        except Exception as de:
            log.warning(f"Response decode failed: {de}")
            text = str(response)
        parsed = None
        try:
            parsed = json.loads(text.strip())
        except Exception:
            if 'data:' in text:
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                for l in reversed(lines):
                    if not l.startswith('data:'):
                        continue
                    payload = l[5:].strip()
                    if payload == '[DONE]':
                        continue
                    try:
                        parsed = json.loads(payload)
                        break
                    except Exception:
                        pass
            if parsed is None and hasattr(response, 'json'):
                try:
                    parsed = response.json()
                except Exception:
                    parsed = None

        if isinstance(parsed, dict):
            # 检查是否是错误响应
            if 'code' in parsed and parsed.get('code') != 200:
                error_message = parsed.get('message', 'Unknown error')
                log.error(f"AssemblyAI returned error: {parsed.get('code')} - {error_message}")
                raise HTTPException(
                    status_code=parsed.get('code', 500),
                    detail=f"AssemblyAI error: {error_message}"
                )
            
            # AssemblyAI 返回 OpenAI 格式，直接使用或进行微调
            openai_response = assembly_response_to_openai(parsed, model)
        else:
            openai_response = {
                "id": str(uuid.uuid4()),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": text.strip()},
                    "finish_reason": "stop"
                }]
            }
        # 如果最终choices为空，构造一个兜底消息避免前端空白
        try:
            if isinstance(openai_response, dict):
                ch = openai_response.get('choices')
                if isinstance(ch, list) and len(ch) == 0:
                    fallback_content = ''
                    if isinstance(parsed, dict):
                        fallback_content = str(parsed.get('output_text') or parsed.get('text') or '')
                    if not fallback_content:
                        fallback_content = text.strip()
                    openai_response['choices'] = [{
                        'index': 0,
                        'message': {'role': 'assistant', 'content': fallback_content},
                        'finish_reason': 'stop'
                    }]
        except Exception:
            pass

        log.info(f"RES model={model} status=OK")
        log.debug(f"RES Details - Converted response: {json.dumps(openai_response, ensure_ascii=False)[:1000]}...")
        return JSONResponse(content=openai_response)
    except Exception as e:
        try:
            sample = (text[:200] + '...') if isinstance(text, str) and len(text) > 200 else text
            log.error(f"RES model={model} status=FAIL conversion_error sample={sample}")
            log.debug(f"RES Details - Conversion error: {str(e)}, Full text: {text[:500]}...")
        except Exception:
            log.error(f"RES model={model} status=FAIL conversion_error")
        raise HTTPException(status_code=500, detail="Response conversion failed")

async def fake_stream_response_for_assembly(openai_request: ChatCompletionRequest) -> StreamingResponse:
    """AssemblyAI 的假流式：周期心跳 + 最终内容块"""
    async def stream_generator():
        try:
            log.debug(f"Starting fake stream for model: {openai_request.model}")
            
            # 发送心跳
            heartbeat = {
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(heartbeat)}\n\n".encode()
            log.debug("Sent initial heartbeat")
            
            # 异步发送实际请求
            async def get_response():
                return await send_assembly_request(openai_request, False)
            
            # 创建请求任务
            response_task = create_managed_task(get_response(), name="openai_fake_stream_request")
            
            try:
                # 每3秒发送一次心跳，直到收到响应
                heartbeat_count = 0
                while not response_task.done():
                    await asyncio.sleep(3.0)
                    if not response_task.done():
                        heartbeat_count += 1
                        yield f"data: {json.dumps(heartbeat)}\n\n".encode()
                        log.debug(f"Sent heartbeat #{heartbeat_count}")
                
                # 获取响应结果
                response = await response_task
                log.debug(f"Received response after {heartbeat_count} heartbeats")
                
            except asyncio.CancelledError:
                # 取消任务并传播取消
                response_task.cancel()
                try:
                    await response_task
                except asyncio.CancelledError:
                    pass
                raise
            except Exception as e:
                # 取消任务并处理其他异常
                response_task.cancel()
                try:
                    await response_task
                except asyncio.CancelledError:
                    pass
                log.error(f"Fake streaming request failed: {e}")
                raise
            
            # 发送实际请求
            # response 已在上面获取
            
            # 处理结果
            # JSONResponse 的内容存储在 body 属性中（bytes）
            if isinstance(response, JSONResponse):
                # JSONResponse 的 body 是 bytes，需要解码
                body_str = response.body.decode('utf-8') if isinstance(response.body, bytes) else str(response.body)
            elif hasattr(response, 'body'):
                body_str = response.body.decode('utf-8') if isinstance(response.body, bytes) else str(response.body)
            elif hasattr(response, 'content'):
                body_str = response.content.decode('utf-8') if isinstance(response.content, bytes) else str(response.content)
            elif hasattr(response, 'text'):
                body_str = response.text
            else:
                body_str = str(response)
            
            try:
                response_data = json.loads(body_str)
                log.debug(f"Parsed response data: {json.dumps(response_data, ensure_ascii=False)[:500]}...")

                # 检查是否是错误响应（支持多种错误格式）
                error_message = None
                error_type = "error"
                error_code = ""
                
                # 格式1: {"error": {"message": "...", "type": "...", "code": "..."}}
                if "error" in response_data:
                    error_info = response_data["error"]
                    error_message = error_info.get("message", "Unknown error")
                    error_type = error_info.get("type", "error")
                    error_code = error_info.get("code", "")
                # 格式2: {"code": 400, "message": "..."} (AssemblyAI 格式)
                elif "code" in response_data and response_data.get("code") != 200:
                    error_message = response_data.get("message", "Unknown error")
                    error_code = response_data.get("code", "")
                    error_type = "api_error"
                
                if error_message:
                    log.warning(f"Error response in fake stream: {error_message} (type: {error_type}, code: {error_code})")
                    
                    # 构建用户友好的错误消息
                    user_message = error_message
                    if error_code == "no_available_keys":
                        user_message = "所有 API 密钥已被禁用，无法处理请求。请在管理面板中启用至少一个密钥。"
                    elif "processing error" in str(error_message).lower():
                        user_message = f"模型处理错误: {error_message}。请检查请求格式或尝试其他模型。"
                    elif error_type == "invalid_request_error":
                        user_message = f"请求错误: {error_message}"
                    elif error_type == "api_error":
                        user_message = f"API 错误: {error_message}"
                    
                    # 以流式格式返回错误信息（符合 OpenAI 格式）
                    error_chunk = {
                        "id": str(uuid.uuid4()),
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": openai_request.model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": user_message
                            },
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n".encode()
                    yield b"data: [DONE]\n\n"
                    return

                # 从响应中提取内容和工具调用（适配 AssemblyAI 的多 choices 格式）
                all_content_parts = []
                all_tool_calls = []
                has_tool_use = False
                
                if "choices" in response_data and response_data["choices"]:
                    for choice in response_data["choices"]:
                        msg = choice.get("message", {})
                        content = msg.get("content")
                        if content and isinstance(content, str) and content.strip():
                            all_content_parts.append(content)
                        
                        # 收集并修复工具调用
                        raw_tool_calls = msg.get("tool_calls") or []
                        for tc in raw_tool_calls:
                            fixed_tc = {
                                "id": tc.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                                "type": tc.get("type", "function"),
                                "function": {}
                            }
                            func = tc.get("function", {})
                            fixed_tc["function"]["name"] = func.get("name", "")
                            args = func.get("arguments", {})
                            
                            # [修复] 参数名映射: 模型生成的 XML 可能使用错误的参数名
                            # 例如 read_file: file_path -> path
                            if fixed_tc["function"]["name"] == "read_file":
                                if isinstance(args, dict) and "file_path" in args:
                                    args["path"] = args.pop("file_path")
                                elif isinstance(args, str):
                                    try:
                                        args_dict = json.loads(args)
                                        if "file_path" in args_dict:
                                            args_dict["path"] = args_dict.pop("file_path")
                                            args = args_dict
                                    except json.JSONDecodeError:
                                        pass
                            
                            if isinstance(args, dict):
                                fixed_tc["function"]["arguments"] = json.dumps(args, ensure_ascii=False)
                            elif isinstance(args, str):
                                fixed_tc["function"]["arguments"] = args
                            else:
                                fixed_tc["function"]["arguments"] = "{}"
                            all_tool_calls.append(fixed_tc)
                        
                        # 检查 finish_reason
                        fr = choice.get("finish_reason", "")
                        if fr in ("tool_use", "tool_calls"):
                            has_tool_use = True
                
                content = " ".join(all_content_parts) if all_content_parts else ""
                
                # [新增] 检查并解析 XML 工具调用 (针对 Gemini/Haiku 等模型返回 XML 的情况)
                if "<function_calls>" in content:
                    log.info(f"[XML Parser] Detected XML tool calls in content, parsing...")
                    content, xml_tool_calls = _parse_xml_tool_calls(content)
                    if xml_tool_calls:
                        log.info(f"[XML Parser] Extracted {len(xml_tool_calls)} XML tool calls")
                        if not all_tool_calls:
                            all_tool_calls = []
                        all_tool_calls.extend(xml_tool_calls)
                        has_tool_use = True
                
                tool_calls = all_tool_calls if all_tool_calls else None
                reasoning_content = ""
  
                # 如果没有正常内容但有思维内容，给出警告
                if not content and reasoning_content:
                    log.warning("Fake stream response contains only thinking content")
                    content = "[模型正在思考中，请稍后再试或重新提问]"
                
                log.info(f"[TOOL_DEBUG] Extracted content length: {len(content)}, tool_calls count: {len(all_tool_calls)}")
                
                # 如果有内容或工具调用，都需要返回
                if content or tool_calls:
                    # 构建响应块，包括思维内容（如果有）和工具调用
                    
                    # 转换usageMetadata为OpenAI格式（兼容多种格式）
                    usage_raw = response_data.get("usage") or {}
                    prompt_tokens = usage_raw.get("prompt_tokens") or usage_raw.get("input_tokens", 0)
                    completion_tokens = usage_raw.get("completion_tokens") or usage_raw.get("output_tokens", 0)
                    cached_tokens = usage_raw.get("cached_tokens") or usage_raw.get("input_cached_tokens", 0)
                    
                    usage = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": usage_raw.get("total_tokens", prompt_tokens + completion_tokens),
                        # 添加详细的 token 信息以支持 LobeChat 等客户端显示
                        "prompt_tokens_details": {
                            "cached_tokens": cached_tokens,
                            "audio_tokens": 0
                        },
                        "completion_tokens_details": {
                            "reasoning_tokens": 0,
                            "audio_tokens": 0,
                            "accepted_prediction_tokens": 0,
                            "rejected_prediction_tokens": 0
                        }
                    } if usage_raw else None

                    # 确定 finish_reason
                    finish_reason = "tool_calls" if has_tool_use else "stop"
                    
                    # 检查是否启用全局假流式渐进输出
                    try:
                        from src.storage_adapter import get_storage_adapter
                        adapter = await get_storage_adapter()
                        fake_stream_enabled = await adapter.get_config("fake_stream_enabled", False)
                        fake_stream_speed = await adapter.get_config("fake_stream_speed", 100)
                    except Exception:
                        fake_stream_enabled = False
                        fake_stream_speed = 100
                    
                    if fake_stream_enabled and content and not tool_calls:
                        # 渐进式流式输出：按速度逐块返回内容
                        log.info(f"Fake stream progressive output: speed={fake_stream_speed} chars/s, content_len={len(content)}")
                        
                        # 计算每块大小和间隔
                        # 例如: 100 chars/s, 每 50ms 输出 5 个字符
                        interval_ms = 50  # 每 50ms 输出一次
                        chars_per_chunk = max(1, int(fake_stream_speed * interval_ms / 1000))
                        
                        response_id = str(uuid.uuid4())
                        
                        # 逐块输出内容（所有 chunk 的 finish_reason 都为 null）
                        for i in range(0, len(content), chars_per_chunk):
                            chunk_content = content[i:i + chars_per_chunk]
                            is_last_content_chunk = (i + chars_per_chunk >= len(content))
                            
                            chunk_delta = {"role": "assistant", "content": chunk_content}
                            
                            # 最后一块内容添加 reasoning_content（如果有）
                            if is_last_content_chunk and reasoning_content:
                                chunk_delta["reasoning_content"] = reasoning_content
                            
                            content_chunk = {
                                "id": response_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": openai_request.model,
                                "choices": [{
                                    "index": 0,
                                    "delta": chunk_delta,
                                    "finish_reason": None  # 内容 chunk 不设置 finish_reason
                                }]
                            }
                            
                            yield f"data: {json.dumps(content_chunk)}\n\n".encode()
                            
                            # 等待间隔（非最后一块）
                            if not is_last_content_chunk:
                                await asyncio.sleep(interval_ms / 1000)
                        
                        # 发送单独的结束 chunk（包含 finish_reason 和 usage）
                        finish_chunk = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": openai_request.model,
                            "choices": [{
                                "index": 0,
                                "delta": {},  # 空 delta
                                "finish_reason": finish_reason
                            }]
                        }
                        if usage:
                            finish_chunk["usage"] = usage
                        yield f"data: {json.dumps(finish_chunk)}\n\n".encode()
                    else:
                        # 一次性输出（原逻辑，但分离结束 chunk）
                        response_id = str(uuid.uuid4())
                        delta = {"role": "assistant"}
                        
                        # 添加 content（如果有）
                        if content:
                            delta["content"] = content
                        
                        # 添加 reasoning_content（如果有）
                        if reasoning_content:
                            delta["reasoning_content"] = reasoning_content
                        
                        # 添加 tool_calls（如果有）
                        if tool_calls:
                            delta["tool_calls"] = tool_calls

                        # 发送内容 chunk（finish_reason 为 null）
                        content_chunk = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": openai_request.model,
                            "choices": [{
                                "index": 0,
                                "delta": delta,
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(content_chunk)}\n\n".encode()

                        # 发送单独的结束 chunk（包含 finish_reason 和 usage）
                        finish_chunk = {
                            "id": response_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": openai_request.model,
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": finish_reason
                            }]
                        }
                        if usage:
                            finish_chunk["usage"] = usage
                        yield f"data: {json.dumps(finish_chunk)}\n\n".encode()
                else:
                    log.warning(f"No content found in response: {response_data}")
                    # 如果完全没有内容，提供默认回复
                    error_chunk = {
                        "id": str(uuid.uuid4()),
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "amb2api-streaming",
                        "choices": [{
                            "index": 0,
                            "delta": {"role": "assistant", "content": "[响应为空，请重新尝试]"},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n".encode()
            except json.JSONDecodeError:
                error_chunk = {
                    "id": str(uuid.uuid4()),
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                        "model": "amb2api-streaming",
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": body_str},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(error_chunk)}\n\n".encode()
            
            yield "data: [DONE]\n\n".encode()
            
        except Exception as e:
            log.error(f"Fake streaming error: {e}")
            error_chunk = {
                "id": str(uuid.uuid4()),
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "gcli2api-streaming",
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": f"Error: {str(e)}"},
                    "finish_reason": "stop"
                }]
            }
            yield f"data: {json.dumps(error_chunk)}\n\n".encode()
            yield "data: [DONE]\n\n".encode()

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

async def convert_streaming_response(gemini_response, model: str) -> StreamingResponse:
    """转换流式响应为OpenAI格式"""
    response_id = str(uuid.uuid4())
    
    async def openai_stream_generator():
        try:
            # 处理不同类型的响应对象
            if hasattr(gemini_response, 'body_iterator'):
                # FastAPI StreamingResponse
                async for chunk in gemini_response.body_iterator:
                    if not chunk:
                        continue
                    
                    # 处理不同数据类型的startswith问题
                    if isinstance(chunk, bytes):
                        if not chunk.startswith(b'data: '):
                            continue
                        payload = chunk[len(b'data: '):]
                    else:
                        chunk_str = str(chunk)
                        if not chunk_str.startswith('data: '):
                            continue
                        payload = chunk_str[len('data: '):].encode()
                    try:
                        gemini_chunk = json.loads(payload.decode())
                        openai_chunk = gemini_stream_chunk_to_openai(gemini_chunk, model, response_id)
                        yield f"data: {json.dumps(openai_chunk, separators=(',',':'))}\n\n".encode()
                    except json.JSONDecodeError:
                        continue
            else:
                # 其他类型的响应，尝试直接处理
                log.warning(f"Unexpected response type: {type(gemini_response)}")
                error_chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": "Response type error"},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(error_chunk)}\n\n".encode()
            
            # 发送结束标记
            yield "data: [DONE]\n\n".encode()
            
        except Exception as e:
            log.error(f"Stream conversion error: {e}")
            error_chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": f"Stream error: {str(e)}"},
                    "finish_reason": "stop"
                }]
            }
            yield f"data: {json.dumps(error_chunk)}\n\n".encode()
            yield "data: [DONE]\n\n".encode()

    return StreamingResponse(openai_stream_generator(), media_type="text/event-stream")