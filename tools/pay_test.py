"""
Stripe 支付测试脚本

用于测试 Stripe Payment Methods API
"""
import httpx
import json
from typing import Dict, Any, Optional


def create_payment_method(
    card_number: str = "5524612497969780",
    card_cvc: str = "069",
    card_exp_month: str = "08",
    card_exp_year: str = "28",
    billing_name: str = "Chris Moore",
    api_key: str = "pk_live_7ystzDhF9zYIUfZSLsXyRHHj",
    guid: str = "398a8eee-7803-4ea7-a2bd-0f5ef1606b99f28934",
    muid: str = "77c74688-3bb6-436f-8061-89fd7d7f8059c15021",
    sid: str = "3b4e5593-8030-4b2a-a08b-506080018cd225ab31",
    hcaptcha_token: Optional[str] = "P1_eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJwZCI6MCwiZXhwIjoxNzY0NDI2OTQ3LCJjZGF0YSI6InM4WWxsTWVwdHI2VW1IdlluREpORGphSEJkKzVZTWdkN3BFNlZTeGhqTkFDbDY5UFExT1Ewd2thMkIrbmVLUms4Mk9yQzVyYi8xN29XLzhuYVBGUExoZldieTdaS1pkOGNLNkJ5M01EUHNoVkl4dDV3Z3J2V1hMNzFyYmhFd0JGUExxUXVjYTBLK0FQZWJWaDM5L0FzdEJVZkJYVHFVVTZ2UGFCTkZPLy9xZjV4eVVxdm43dEFFTE5CZzBlOUdqRmFMUkNDWXZPYUhMcUVYczIiLCJwYXNza2V5IjoiOEFUL1FqQ0JRUlNrdDdBZTgxdTBMY0xuSWNnbFBkZnE0ZVdvUXEyVHYySjg1U0h3VzBTYW5xUy9mMFFvVXJnc1MzVGprd2gxUG5rK0NER0VTMnVjQzVkVlNrRzFqSlhVU3hYUmVRRVpZcnVoTzRzMGRFQ3pUUkl5bGNlZEgzWlJZaXpGajdIeGw0S0c0Yzh1UGFncEY5Y1JUWjVNTXdYZUV4Sm1kbWpnT0dhazN6c1VLNWlobWVEa0pPRFUvQ2tiYXAvK0RzMVkwTnRMV3FQOTAySkF2Y09jb1F5aWNEd1BTUURpRFpaUUsvKy9ndmpsVEhMT0c2MmorY1dSUWlkZUpYSTFvK1BvbXN0VWJwR1pMQUl2M0YyQTgxM3RtdkNGdy9TbXl0VVNERENGQjdIdXNzclYzaUc5ZUd0S2ZEcVFGNlo1RWdpbFoyVXptTUkrUFJPbktIdU9vVzZIUU5JYm53UUhNanh3ZHc4bXZWd1l0QlZFZWw0cGJtVEgyMlZsUGhEWjVST29XaXhaSGwzeVdqNGxEZ0tlckptT3g5SmdFWHpoZ1dMTittd2oxZnc2c29JQmdCOURGUzI0UXF6NnpsdlZMWEx2d0dCdXpON0FkeGd0cXpxT1p1cXJNL21MSDBPMWpad2xhNmF3N2JkcWtmc3I2MU5CbFFyYmNhR1NiUGR2ekt2bkJhZFJkdGxFSlVrS1F0M0V6cVNIaXJSZmYvNXVaTHlDZ1o2b1ZFUUFONzZCNmR1NWYzM0xvdFJsUlRhdStLdC9jWW1iZlZPSUw5c20xZURkRHM4YVNLRWJHc2c1TDYwWTlzaE4vcXhnTU5uTVVCdTFYRVJCK2xMMko1NVdPcFNVajVQZ1N5QmJvanNjN21UdjE1NksweE5CdTF1UGM4Yk0rQ1RVU29JejE5KzVxOUV2SDVEdXA0ckZzeHB2bCtzU2I3QjUrRlZJWExsaHNsaUxtUnNPdXBwUVFDZ1djN3NwT2tPTDBhc042VW9xUnVTVEM3eUc2RWF6ZHhSQWkwemNZYWNoTnQwVUtjbUUyVE5wU095UWpDUVZneVFFUWN3M1pDQ2U2cnllMXVPb01vTmRnbFg4cStWUzJPNFprcEF5bzllbDRsOU91Z3g2YWRDSDZEZSsxSmVDS2RHbmRPRWxsNDlUbkgvVzNVcWpTSkJ4dDZVekZNVzlScDNIM3hoQ1RrQWRyL2orWncrbWh0ZjROK1dha0JYbHhmamxmTFBRdDRybE0zNjV2Mmg1ZGVmWjhZWlE4dC80Y2ZwM2dWYWpSSzhCRThmWWdPZGNHR0tYdU5qR1hKQVBKTFphMnNlU1ZGWkNoVTk4NG9WVnpjK1lQWVJoU1Z2R1kxdXFVcHcydkFndFlQYXVjSlpMbGFrbWRVQkR3SlIxd3BuVnAwNDQ3RmlHamN3eVkwNjJFOHNhTnZiRHMvOStJajhjTm4vQkdBN1NPcFkrMHRIdDUwSThBSGZGTG15VlYyQXFXMHZ3K2hrQ3YrUCtRZ3BmSGV2OXNzZk1qL013S0UwZDRhYjBTZ2xveElmNTFyV1IyMWUva3pta2kzQmpjVkZXMWdKZmhpWXg2UXRqdUtpWmY0dkxIcFE3ZzVnZVhBT0VlYjgwckpqSTEyaVZtcEhGVU5veDF2T1VqVTVOWXFUZU9TSGpuMmJyZkZES3hDK1RxbGJBdTlCbDNONzFqNC92YmhmN1liZFVON2RJbmtwUDlYZHZmMnh4V1loTk9UWHZjVGsrOXlOQlpibzQzRGVQRG1KYlJuYkNjTlpqRDlSdkN4WjZrVGhwNnJWQ3VZNnMvRUVVbnNqbnhtTVkwRkF3UVBSeERPanFFTG00ekdhL2U2Rmk2dWVoeUVrdGZNMU43SWZsU21hRmdPV0FEMEdYOWN2NHI5N1RSZ1YwZENVeTBzR3l6VDVNdXk0LzZpbVI1QmN4Z1I4V2x6WXRIOHowU2JzUjdFeWNPWWI3R0p3K1RTY1hmN0N2Z2JXT0RVYTBwbG83TGpvcnc4ZFFsSjFVY3pKdStMeDJEa0pZbEpRczhRbVBlVzc2d0dDV2dQT2NlTEFSSENlUXE0SXFFL3RrNkRYMGJUVHE3c2ZyWWMrQ0hoY3U5STd5Tkp0RHQ5KzlTZHVDZ3piK01sMmtsY2hFRGhvZmdQS1N1TjNFM2JQb0FJa0RmY0NYdWEyVmNWaEdkYVVONnFVYXE5a0RNbktqeEM4ejZNNDdqWUx2TnBXRnZrVEJUcG1ES1ZCMkgzdVhURnFlKzBBR0syeldiZ0I0L3Z1UytlTXJnUTVjbzB4blZLbWRDU01HRDk2ZGxvbklLU3ROMFdSR2Y5Y1FrRXhiekQzWk8vaHowN1hkS1FtREwwcVA1aVl2N0RNdUVkSDE4S3NIZGgyalpGdWJ4NWhzekVkRVFBWlRnQkZaNkxKeC9iaTBRdlJqN0UwVmNtWE1BSjRlamZwRnVOVFNDNkhKdG5tdENkK2FYZHgyOFVVTU1QSmY2QmN4ZXZmSnhIL25lcG9aSHI4T0ZkYXUwZXF1ZlRJL3JCL1N6dTJlUHFxRzA4U1VtT2ZGUEUvRzZtZkhMM295Q3h1OTJHTFVmTHVhTzFUamQ5UWJQcjA2WVdGdk1ubzloWmxVMnVzSElTdFNrUjNqOER3Q1VsODgrdkF0ZGcxRWJLR2dBWkFSeFZ5Q3ppelRtUEg1c0lsZ3M3NWhKdk1iZCswQzY2bVRWUXZseFZDb3pBbjRRVlN1K0ZjeTZrb3hwb0JZZ3dlZ0JRPT0iLCJrciI6IjNhODk5YTBlIiwic2hhcmRfaWQiOjM2MjQwNjk5Nn0.pciu8Kf9fN-XbaogMvuHZ_KJHmiNnsj6tu9Q7SM6DoM",
) -> Dict[str, Any]:
    """
    创建 Stripe 支付方式
    
    Args:
        card_number: 卡号
        card_cvc: CVC 安全码
        card_exp_month: 过期月份 (MM)
        card_exp_year: 过期年份 (YY)
        billing_name: 账单姓名
        api_key: Stripe API 密钥
        guid: 浏览器 GUID
        muid: 浏览器 MUID
        sid: 会话 ID
        hcaptcha_token: hCaptcha token (可选)
    
    Returns:
        支付方式的响应数据
    """
    url = "https://api.stripe.com/v1/payment_methods"
    
    # 构建表单数据
    data = {
        "type": "card",
        "billing_details[name]": billing_name,
        "card[number]": card_number,
        "card[cvc]": card_cvc,
        "card[exp_month]": card_exp_month,
        "card[exp_year]": card_exp_year,
        "guid": guid,
        "muid": muid,
        "sid": sid,
        "pasted_fields": "number",
        "payment_user_agent": "stripe.js/cba9216f35; stripe-js-v3/cba9216f35; split-card-element",
        "referrer": "https://www.assemblyai.com",
        "time_on_page": "13029446",
        "client_attribution_metadata[client_session_id]": "55d4b3f3-9ccb-439d-91d5-9ad43643bd95",
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "split-card-element",
        "client_attribution_metadata[merchant_integration_version]": "2017",
        "key": api_key,
    }
    
    # 添加 hcaptcha_token（如果有）
    if hcaptcha_token:
        data["radar_options[hcaptcha_token]"] = hcaptcha_token
    
    # 设置请求头
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    }
    
    try:
        print(f"正在调用 Stripe API: {url}")
        print(f"卡号: {card_number[:4]}****{card_number[-4:]}")
        print(f"持卡人: {billing_name}")
        print(f"过期日期: {card_exp_month}/{card_exp_year}")
        
        # 发送 POST 请求
        with httpx.Client() as client:
            response = client.post(url, data=data, headers=headers)
            
            print(f"\n响应状态码: {response.status_code}")
            
            # 解析响应
            if response.status_code == 200:
                result = response.json()
                print("\n✅ 支付方式创建成功!")
                print(f"Payment Method ID: {result.get('id')}")
                print(f"卡品牌: {result.get('card', {}).get('brand')}")
                print(f"卡号后四位: {result.get('card', {}).get('last4')}")
                print(f"过期日期: {result.get('card', {}).get('exp_month')}/{result.get('card', {}).get('exp_year')}")
                return result
            else:
                print(f"\n❌ 请求失败!")
                print(f"错误信息: {response.text}")
                try:
                    error_data = response.json()
                    return error_data
                except:
                    return {"error": response.text, "status_code": response.status_code}
                
    except httpx.RequestError as e:
        print(f"\n❌ 请求异常: {str(e)}")
        return {"error": str(e)}


def test_payment_method():
    """
    测试函数 - 使用示例数据
    """
    # 使用默认参数调用
    result = create_payment_method()
    
    # 打印完整响应
    print("\n" + "="*50)
    print("完整响应数据:")
    print("="*50)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result


def get_user_input_and_create_payment() -> Dict[str, Any]:
    """
    交互式获取用户输入并立即创建支付方式
    按照顺序：卡号信息 -> 创建支付方式 -> Cookie信息 -> 付款金额信息
    """
    print("="*70)
    print("Stripe 支付对接脚本 - 交互式输入")
    print("="*70)
    
    # ========== 第一步：输入卡号相关信息 ==========
    print("\n" + "="*70)
    print("【第一步】请输入卡号相关信息")
    print("="*70)
    
    card_number = input("请输入卡号: ").strip()
    if not card_number:
        print("❌ 卡号不能为空")
        return None
    
    card_cvc = input("请输入 CVC 安全码: ").strip()
    if not card_cvc:
        print("❌ CVC 安全码不能为空")
        return None
    
    card_exp_month = input("请输入过期月份 (MM，例如: 08): ").strip()
    if not card_exp_month:
        print("❌ 过期月份不能为空")
        return None
    
    card_exp_year = input("请输入过期年份 (YY，例如: 28): ").strip()
    if not card_exp_year:
        print("❌ 过期年份不能为空")
        return None
    
    billing_name = input("请输入持卡人姓名 (默认: Chris Moore): ").strip()
    if not billing_name:
        billing_name = "Chris Moore"
        print(f"使用默认值: {billing_name}")
    
    # 可选：hCaptcha token
    print("\n提示: hCaptcha token 是可选的")
    print("     输入方式:")
    print("     - 直接粘贴 token 内容（支持多行，粘贴后按空行结束）")
    print("     - 输入文件路径（例如: /Users/liangfeng/token.txt 或 ./token.txt）")
    print("     - 直接回车跳过，使用默认值")
    print()
    
    hcaptcha_input = input("请输入 hCaptcha token 内容或文件路径 (可选，直接回车跳过): ").strip()
    
    if not hcaptcha_input:
        hcaptcha_token = None
        print("将使用默认 hCaptcha token")
    elif hcaptcha_input.lower() == 'skip':
        hcaptcha_token = None
        print("将使用默认 hCaptcha token")
    else:
        # 检查是否是文件路径
        import os
        is_file_path = False
        
        # 判断是否是文件路径：以 / 或 ./ 或 ~/ 开头，或者以 .txt 结尾，或者包含路径分隔符
        if (hcaptcha_input.startswith('/') or 
            hcaptcha_input.startswith('./') or 
            hcaptcha_input.startswith('~/') or
            hcaptcha_input.endswith('.txt') or
            '/' in hcaptcha_input or
            '\\' in hcaptcha_input):
            file_path = os.path.expanduser(hcaptcha_input)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                is_file_path = True
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        hcaptcha_token = f.read().strip()
                    print(f"\n✅ 从文件读取 token")
                    print(f"   文件路径: {file_path}")
                    print(f"   Token 长度: {len(hcaptcha_token)} 字符")
                    # 显示 token 的前后部分供比对
                    if len(hcaptcha_token) > 50:
                        print(f"   Token 开头: {hcaptcha_token[:30]}...")
                        print(f"   Token 结尾: ...{hcaptcha_token[-30:]}")
                    else:
                        print(f"   Token 内容: {hcaptcha_token}")
                except Exception as e:
                    print(f"⚠️  读取文件失败: {e}")
                    print("将作为 token 内容使用")
                    is_file_path = False
        
        if not is_file_path:
            # 直接输入的内容，支持多行
            hcaptcha_token_lines = [hcaptcha_input]
            print("提示: 如果 token 还没输入完，可以继续输入（空行结束）:")
            while True:
                try:
                    line = input()
                    if not line.strip():
                        break
                    hcaptcha_token_lines.append(line)
                except (EOFError, KeyboardInterrupt):
                    break
            hcaptcha_token = "".join(hcaptcha_token_lines).strip()
            if hcaptcha_token:
                print(f"\n✅ 已接收 token")
                print(f"   Token 长度: {len(hcaptcha_token)} 字符")
                # 显示 token 的前后部分供比对
                if len(hcaptcha_token) > 50:
                    print(f"   Token 开头: {hcaptcha_token[:30]}...")
                    print(f"   Token 结尾: ...{hcaptcha_token[-30:]}")
                else:
                    print(f"   Token 内容: {hcaptcha_token}")
            else:
                hcaptcha_token = None
                print("将使用默认 hCaptcha token")
    
    # ========== 立即创建支付方式 ==========
    print("\n" + "="*70)
    print("【正在创建支付方式...】")
    print("="*70)
    
    kwargs = {}
    if hcaptcha_token:
        kwargs["hcaptcha_token"] = hcaptcha_token
    
    payment_result = create_payment_method(
        card_number=card_number,
        card_cvc=card_cvc,
        card_exp_month=card_exp_month,
        card_exp_year=card_exp_year,
        billing_name=billing_name,
        **kwargs
    )
    
    # 检查是否成功
    if "error" in payment_result or not payment_result.get("id"):
        print("\n" + "="*70)
        print("❌ 创建支付方式失败!")
        print("="*70)
        print("错误详情:")
        print(json.dumps(payment_result, indent=2, ensure_ascii=False))
        return None
    
    payment_method_id = payment_result.get("id")
    print("\n" + "="*70)
    print("✅ 支付方式创建成功!")
    print("="*70)
    print(f"Payment Method ID: {payment_method_id}")
    print(f"卡品牌: {payment_result.get('card', {}).get('brand', 'N/A')}")
    print(f"卡号后四位: {payment_result.get('card', {}).get('last4', 'N/A')}")
    print(f"过期日期: {payment_result.get('card', {}).get('exp_month', 'N/A')}/{payment_result.get('card', {}).get('exp_year', 'N/A')}")
    print("="*70)
    
    # ========== 第二步：输入 Cookie 信息 ==========
    import os
    cookies = None
    
    # 循环输入 Cookie，直到成功读取或用户取消
    while cookies is None:
        print("\n" + "="*70)
        print("【第二步】请输入 Cookie 信息")
        print("="*70)
        print("提示: 从浏览器开发者工具中复制完整的 Cookie 值")
        print("     路径: Network -> 找到请求 -> Headers -> Request Headers -> Cookie")
        print("     或者直接复制整个 Cookie 字符串")
        print()
        
        print("输入方式:")
        print("     - 直接粘贴 Cookie 内容（支持多行，粘贴后按空行结束）")
        print("     - 输入文件路径（例如: /Users/liangfeng/cookie.txt 或 ./cookie.txt）")
        print()
        
        cookie_input = input("请输入 Cookie 内容或文件路径: ").strip()
        
        if not cookie_input:
            print("❌ Cookie 不能为空，升级接口需要 Cookie 进行认证")
            retry = input("是否重新输入? (y/n，默认: y): ").strip().lower()
            if retry and retry not in ['y', 'yes', '是', '']:
                return None
            continue
        
        # 检查是否是文件路径
        is_file_path = False
        
        # 判断是否是文件路径：先检查第一行输入
        # 如果第一行看起来像文件路径，直接尝试读取
        # 如果第一行不是文件路径，但下一行输入了文件路径，也尝试读取
        potential_file_path = cookie_input
        
        # 判断是否是文件路径
        looks_like_file_path = (
            potential_file_path.startswith('/') or 
            potential_file_path.startswith('./') or 
            potential_file_path.startswith('~/') or
            potential_file_path.endswith('.txt') or
            '/' in potential_file_path or
            '\\' in potential_file_path
        )
        
        if looks_like_file_path:
            # 转换为绝对路径
            if potential_file_path.startswith('./'):
                # 相对路径，转换为绝对路径
                file_path = os.path.abspath(potential_file_path)
            else:
                file_path = os.path.expanduser(potential_file_path)
            
            # 检查文件是否存在
            if os.path.exists(file_path) and os.path.isfile(file_path):
                is_file_path = True
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        cookies = f.read().strip()
                    print(f"\n✅ 从文件读取 Cookie")
                    print(f"   文件路径: {file_path}")
                    print(f"   Cookie 长度: {len(cookies)} 字符")
                    # 显示 Cookie 的前后部分供比对
                    if len(cookies) > 100:
                        print(f"   Cookie 开头: {cookies[:50]}...")
                        print(f"   Cookie 结尾: ...{cookies[-50:]}")
                    else:
                        print(f"   Cookie 内容: {cookies[:200]}...")
                    break  # 成功读取，退出循环
                except Exception as e:
                    print(f"\n❌ 读取文件失败: {e}")
                    print(f"   文件路径: {file_path}")
                    retry = input("是否重新输入? (y/n，默认: y): ").strip().lower()
                    if retry and retry not in ['y', 'yes', '是', '']:
                        return None
                    continue
            else:
                # 文件不存在，明确提示错误
                print(f"\n❌ 文件不存在: {file_path}")
                print(f"   请检查文件路径是否正确")
                print(f"   当前工作目录: {os.getcwd()}")
                retry = input("是否重新输入? (y/n，默认: y): ").strip().lower()
                if retry and retry not in ['y', 'yes', '是', '']:
                    return None
                continue
        
        # 如果第一行不是文件路径，检查下一行输入
        if not is_file_path and not looks_like_file_path:
            # 先检查第一行是否可能是文件路径（但文件不存在）
            # 如果第一行很短（比如只是"2"），可能是误输入，等待下一行
            if len(cookie_input) <= 5 and not cookie_input.startswith('/'):
                print("提示: 如果这是文件路径，请直接输入完整路径")
                print("     如果这是 Cookie 内容，可以继续输入（空行结束）:")
                # 读取下一行
                try:
                    next_line = input().strip()
                    if next_line:
                        # 检查下一行是否是文件路径
                        next_looks_like_file = (
                            next_line.startswith('/') or 
                            next_line.startswith('./') or 
                            next_line.startswith('~/') or
                            next_line.endswith('.txt') or
                            '/' in next_line
                        )
                        if next_looks_like_file:
                            # 转换为绝对路径
                            if next_line.startswith('./'):
                                file_path = os.path.abspath(next_line)
                            else:
                                file_path = os.path.expanduser(next_line)
                            
                            if os.path.exists(file_path) and os.path.isfile(file_path):
                                is_file_path = True
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        cookies = f.read().strip()
                                    print(f"\n✅ 从文件读取 Cookie")
                                    print(f"   文件路径: {file_path}")
                                    print(f"   Cookie 长度: {len(cookies)} 字符")
                                    # 显示 Cookie 的前后部分供比对
                                    if len(cookies) > 100:
                                        print(f"   Cookie 开头: {cookies[:50]}...")
                                        print(f"   Cookie 结尾: ...{cookies[-50:]}")
                                    else:
                                        print(f"   Cookie 内容: {cookies[:200]}...")
                                    break  # 成功读取，退出循环
                                except Exception as e:
                                    print(f"\n❌ 读取文件失败: {e}")
                                    print(f"   文件路径: {file_path}")
                                    retry = input("是否重新输入? (y/n，默认: y): ").strip().lower()
                                    if retry and retry not in ['y', 'yes', '是', '']:
                                        return None
                                    continue
                            else:
                                print(f"\n❌ 文件不存在: {file_path}")
                                print(f"   请检查文件路径是否正确")
                                retry = input("是否重新输入? (y/n，默认: y): ").strip().lower()
                                if retry and retry not in ['y', 'yes', '是', '']:
                                    return None
                                continue
                        else:
                            # 下一行不是文件路径，合并作为 Cookie 内容
                            cookie_input = cookie_input + " " + next_line
                except (EOFError, KeyboardInterrupt):
                    pass
        
        if not is_file_path:
            # 直接输入的内容，支持多行
            cookie_lines = [cookie_input]
            print("提示: 如果 Cookie 还没输入完，可以继续输入（空行结束）:")
            while True:
                try:
                    line = input()
                    if not line.strip():
                        break
                    cookie_lines.append(line)
                except (EOFError, KeyboardInterrupt):
                    break
            cookies = " ".join(cookie_lines).strip()
            if not cookies:
                print("❌ Cookie 不能为空，升级接口需要 Cookie 进行认证")
                retry = input("是否重新输入? (y/n，默认: y): ").strip().lower()
                if retry and retry not in ['y', 'yes', '是', '']:
                    return None
                continue
            print(f"\n✅ 已接收 Cookie")
            print(f"   Cookie 长度: {len(cookies)} 字符")
            # 显示 Cookie 的前后部分供比对
            if len(cookies) > 100:
                print(f"   Cookie 开头: {cookies[:50]}...")
                print(f"   Cookie 结尾: ...{cookies[-50:]}")
            else:
                print(f"   Cookie 内容: {cookies[:200]}...")
            break  # 成功读取，退出循环
    
    # ========== 第三步：输入付款金额信息 ==========
    print("\n" + "="*70)
    print("【第三步】请输入付款金额信息")
    print("="*70)
    print("⚠️  重要提示：最低充值金额为 10 美元")
    print("     如果输入金额小于 10 美元，API 可能会返回错误")
    print()
    
    amount_str = input("请输入付款金额 (美元，例如: 10 或 10.5，最低 10): ").strip()
    if not amount_str:
        print("❌ 付款金额不能为空")
        return None
    
    try:
        # 支持小数输入
        amount = float(amount_str)
        if amount < 0:
            print("❌ 付款金额不能为负数")
            return None
        if amount < 10:
            print("⚠️  警告：金额小于 10 美元，API 可能会返回错误")
            confirm = input("是否继续? (y/n，默认: n): ").strip().lower()
            if confirm not in ['y', 'yes', '是']:
                print("已取消，请重新输入 >= 10 美元的金额")
                return None
        # API 可能需要整数（美分），但先保持为 float，让 API 决定
        # 如果 API 需要整数，可以在这里转换：amount = int(amount * 100)
    except ValueError:
        print("❌ 付款金额必须是数字（支持小数，例如: 10.5）")
        return None
    
    print("\n提示: '是否免费' 表示这是一个免费的升级（不收费）")
    print("     即使提供了支付方式，如果选择免费，也不会从卡中扣款")
    print("     通常用于测试或促销活动")
    print()
    is_chargeless_str = input("是否免费升级? (y/n，默认: n): ").strip().lower()
    is_chargeless = is_chargeless_str in ['y', 'yes', '是']
    
    # ========== 汇总信息 ==========
    print("\n" + "="*70)
    print("【信息确认】")
    print("="*70)
    print(f"Payment Method ID: {payment_method_id}")
    print(f"卡号: {card_number[:4]}****{card_number[-4:]}")
    print(f"付款金额: ${amount}")
    print(f"是否免费: {'是' if is_chargeless else '否'}")
    print(f"Cookie 长度: {len(cookies)} 字符")
    print()
    
    confirm = input("确认以上信息无误，继续升级账户计划? (y/n，默认: y): ").strip().lower()
    if confirm and confirm not in ['y', 'yes', '是', '']:
        print("已取消操作")
        return None
    
    return {
        "payment_method_id": payment_method_id,
        "payment_result": payment_result,
        "cookies": cookies,
        "amount": amount,
        "is_chargeless": is_chargeless,
    }


def upgrade_account_plan(
    stripe_payment_method_id: str,
    amount: float = 10,
    is_chargeless: bool = False,
    cookies: Optional[str] = None,
) -> Dict[str, Any]:
    """
    升级账户计划
    
    注意：此接口需要先调用 create_payment_method 获取 payment_method_id
    
    Args:
        stripe_payment_method_id: 从 create_payment_method 返回的 payment_method_id
        amount: 金额（美元，支持小数）
        is_chargeless: 是否免费
        cookies: Cookie 字符串（必需），从浏览器开发者工具中复制完整的 Cookie 值
    
    Returns:
        升级计划的响应数据
    """
    url = "https://www.assemblyai.com/dashboard/api/accounts/plans/upgrade"
    
    # 注意：某些 API 可能需要金额为整数（美分），而不是浮点数（美元）
    # 如果 API 返回 500 错误，可以尝试将 amount 转换为整数
    # amount_in_cents = int(amount * 100)  # 转换为美分
    
    data = {
        "stripe_payment_method_id": stripe_payment_method_id,
        "isChargeless": is_chargeless,
        "amount": amount,  # 保持为浮点数，如果 API 需要整数，可能需要转换
    }
    
    # 使用完整的请求头，模拟浏览器行为
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Content-Type": "application/json",
        "Origin": "https://www.assemblyai.com",
        "Priority": "u=1, i",
        "Referer": "https://www.assemblyai.com/dashboard/account/pricing",
        "Sec-Ch-Ua": '"Not(A:Brand";v="99", "Microsoft Edge";v="133", "Chromium";v="133"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
    }
    
    # Cookie 是必需的
    if cookies:
        headers["Cookie"] = cookies
    else:
        print("⚠️  警告: 未提供 Cookie，请求可能会失败")
    
    try:
        print(f"\n正在调用升级接口: {url}")
        print(f"Payment Method ID: {stripe_payment_method_id}")
        print(f"金额: ${amount}")
        print(f"是否免费: {is_chargeless}")
        print(f"\n请求数据:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        with httpx.Client() as client:
            response = client.post(url, json=data, headers=headers)
            print(f"\n响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print("\n✅ 账户计划升级成功!")
                return result
            else:
                print(f"\n❌ 请求失败!")
                print(f"响应头: {dict(response.headers)}")
                print(f"错误信息: {response.text}")
                
                # 分析可能的错误原因
                print(f"\n【错误分析】")
                if response.status_code == 500:
                    print("500 Internal Server Error 可能的原因:")
                    print("1. Cookie 过期或无效 - 请检查 Cookie 是否最新")
                    print("2. 金额格式问题 - API 可能需要整数（美分）而不是浮点数")
                    print("3. 支付方式 ID 与账户不匹配")
                    print("4. 服务器端验证失败")
                    print("5. 缺少必需的请求参数")
                    print("\n建议:")
                    print("- 检查 Cookie 是否从浏览器最新复制")
                    print("- 尝试将金额转换为整数（美分）")
                    print("- 确认支付方式 ID 是否正确")
                
                try:
                    error_data = response.json()
                    return error_data
                except:
                    return {"error": response.text, "status_code": response.status_code}
    except httpx.RequestError as e:
        print(f"\n❌ 请求异常: {str(e)}")
        return {"error": str(e)}


def main():
    """
    主函数：交互式执行完整支付流程
    """
    # 获取用户输入并创建支付方式
    user_input = get_user_input_and_create_payment()
    if not user_input:
        print("\n❌ 流程中断，程序退出")
        return
    
    # 执行升级账户计划
    print("\n" + "="*70)
    print("【正在升级账户计划...】")
    print("="*70)
    
    try:
        upgrade_result = upgrade_account_plan(
            stripe_payment_method_id=user_input["payment_method_id"],
            amount=user_input["amount"],
            is_chargeless=user_input["is_chargeless"],
            cookies=user_input["cookies"],
        )
        
        # 打印最终结果
        print("\n" + "="*70)
        print("【最终结果】")
        print("="*70)
        result = {
            "payment_method": user_input["payment_result"],
            "upgrade": upgrade_result,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 判断是否成功
        if upgrade_result and "error" not in upgrade_result:
            print("\n" + "="*70)
            print("✅ 支付流程执行成功!")
            print("="*70)
            print(f"Payment Method ID: {user_input['payment_method_id']}")
        else:
            print("\n" + "="*70)
            print("⚠️  支付方式创建成功，但升级计划失败")
            print("="*70)
            print("错误详情:")
            print(json.dumps(upgrade_result, indent=2, ensure_ascii=False))
            
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
    except Exception as e:
        print(f"\n\n❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


def create_payment_and_upgrade(
    card_number: str = "5524612497969780",
    card_cvc: str = "069",
    card_exp_month: str = "08",
    card_exp_year: str = "28",
    billing_name: str = "Chris Moore",
    amount: float = 10,
    is_chargeless: bool = False,
    cookies: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    完整的支付流程：先创建支付方式，然后升级账户计划
    
    两个接口的顺序关系：
    1. 先调用 create_payment_method 创建支付方式
    2. 使用返回的 payment_method_id 调用 upgrade_account_plan 升级计划
    """
    print("="*60)
    print("开始完整支付流程")
    print("="*60)
    
    # 步骤 1: 创建支付方式
    print("\n【步骤 1/2】创建支付方式...")
    payment_result = create_payment_method(
        card_number=card_number,
        card_cvc=card_cvc,
        card_exp_month=card_exp_month,
        card_exp_year=card_exp_year,
        billing_name=billing_name,
        **kwargs
    )
    
    if "error" in payment_result or not payment_result.get("id"):
        print("\n❌ 创建支付方式失败，无法继续升级")
        return {"payment_method": payment_result, "upgrade": None}
    
    payment_method_id = payment_result.get("id")
    print(f"\n✅ 获取到 Payment Method ID: {payment_method_id}")
    
    # 步骤 2: 升级账户计划
    print("\n【步骤 2/2】升级账户计划...")
    upgrade_result = upgrade_account_plan(
        stripe_payment_method_id=payment_method_id,
        amount=amount,
        is_chargeless=is_chargeless,
        cookies=cookies,
    )
    
    return {"payment_method": payment_result, "upgrade": upgrade_result}
