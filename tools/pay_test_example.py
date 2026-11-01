"""
使用示例：如何调用升级接口
"""
import os

from pay_test import upgrade_account_plan, create_payment_and_upgrade

# 在本地通过 ASSEMBLY_COOKIE 环境变量提供 Cookie，勿提交真实会话凭据
COOKIE_EXAMPLE = os.environ.get("ASSEMBLY_COOKIE", "")


# 示例 1: 只升级计划（如果已有 payment_method_id）
def example_upgrade_only():
    """示例：只调用升级接口"""
    result = upgrade_account_plan(
        stripe_payment_method_id="pm_example",  # 从 create_payment_method 获取
        amount=10,
        is_chargeless=False,
        cookies=COOKIE_EXAMPLE,  # 使用本地环境变量中的 Cookie
    )
    print(result)


# 示例 2: 完整流程（创建支付方式 + 升级计划）
def example_full_flow():
    """示例：完整的支付流程"""
    result = create_payment_and_upgrade(
        amount=10,
        is_chargeless=False,
        cookies=COOKIE_EXAMPLE,  # 使用本地环境变量中的 Cookie
    )
    print(result)


if __name__ == "__main__":
    if not COOKIE_EXAMPLE:
        raise SystemExit("请先在本地设置 ASSEMBLY_COOKIE 环境变量。")
    # 运行示例
    # example_upgrade_only()
    example_full_flow()
