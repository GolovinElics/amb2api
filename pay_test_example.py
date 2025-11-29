"""
使用示例：如何调用升级接口
"""
from pay_test import upgrade_account_plan, create_payment_and_upgrade

# 从你提供的请求头中复制的完整 Cookie
COOKIE_EXAMPLE = """rs_ga=GA1.1.b269b0d1-810f-4e04-a9b5-534274074859; _ga=GA1.1.b269b0d1-810f-4e04-a9b5-534274074859; _hjSessionUser_2275844=eyJpZCI6IjZmNTNiYjhiLTc3NTYtNTFhNy1hMDNhLTE5M2I3MjFhZDFlMyIsImNyZWF0ZWQiOjE3NjQ0MTMzMDU0NDAsImV4aXN0aW5nIjp0cnVlfQ==; OptanonAlertBoxClosed=2025-11-29T10:48:25.876Z; __stripe_mid=77c74688-3bb6-436f-8061-89fd7d7f8059c15021; OptanonConsent=isGpcEnabled=0&datestamp=Sat+Nov+29+2025+18%3A55%3A52+GMT%2B0800+(%E4%B8%AD%E5%9B%BD%E6%A0%87%E5%87%86%E6%97%B6%E9%97%B4)&version=202503.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A0%2CC0002%3A0%2CC0004%3A0&geolocation=SG%3B&AwaitingReconsent=false; _gcl_au=1.1.1941979093.1764413305.1488214770.1764413316.1764413793; aai_extended_session=eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..5C-eDEK3V1bXh8eY.D6CGhFv6wyffCHw9nstwqMwdv6edUgRHi2gpwie1Db3Dox_EvF1ygtGEToarzURH8NK_f3_8TxhUEuQK5XUJewZLUDc0goyDCs7RYAHoFf2cgtPQabQRrzIwgBghDnYQT9Q0f2Hb0br2v9GaKPOB12uax0-93OAoa8KXsBROCBr8dfSBMlgWIm_mYWsvnUL0etfufiZlFcaGE-IuECEvMOtEb5NerA0u0Ikc58AnTMLtLA.8sFegON30y9hYhR7bU7WaQ; session_token=PyRSIqyVkNux9P1-rsWG2ooNeLSbc7BI23nuaeoiF2CK; _hjSession_2275844=eyJpZCI6IjM1ZmI5OGFlLWMxYjktNDZmMi04ZDFiLWZiZjU2ZjhkZmYxMSIsImMiOjE3NjQ0MjUxMTQ2NjIsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjowLCJzcCI6MX0=; rs_ga_5947MQ8T7P=GS2.1.s1764425114$o2$g1$t1764425138$j36$l0$h0; _ga_F02NWP5ER0=GS2.1.s1764425116$o2$g1$t1764425138$j38$l0$h0; session_jwt=eyJhbGciOiJSUzI1NiIsImtpZCI6Imp3ay1saXZlLWRkOGYxMDc0LTM3ZTMtNGI2YS04YmFiLWY2MWRlY2Q0ZDMwOSIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsicHJvamVjdC1saXZlLTQ4ZmE0YzU2LTcyMjItNDQ3NS05N2NjLTZiMWYzZjdiOGIwOCJdLCJleHAiOjE3NjQ0Mjc1MTQsImh0dHBzOi8vc3R5dGNoLmNvbS9vcmdhbml6YXRpb24iOnsib3JnYW5pemF0aW9uX2lkIjoib3JnYW5pemF0aW9uLWxpdmUtMWViOTI3ZTctNDVkZC00NjJkLTg1ODUtYmNjYjA0ZWFhNjM3Iiwic2x1ZyI6ImdvbG92aW4tMiJ9LCJodHRwczovL3N0eXRjaC5jb20vc2Vzc2lvbiI6eyJpZCI6Im1lbWJlci1zZXNzaW9uLWxpdmUtM2Q4ZWU1NWUtNDAzMi00MGQ0LWI1MGQtYzAzMWU2ZDVlMGRjIiwic3RhcnRlZF9hdCI6IjIwMjUtMTEtMjlUMTA6NTY6MzRaIiwibGFzdF9hY2Nlc3NlZF9hdCI6IjIwMjUtMTEtMjlUMTQ6NDA6MTRaIiwiZXhwaXJlc19hdCI6IjIwMjUtMTItMjlUMTA6NTY6MzRaIiwiYXR0cmlidXRlcyI6eyJ1c2VyX2FnZW50IjoiIiwiaXBfYWRkcmVzcyI6IiJ9LCJhdXRoZW50aWNhdGlvbl9mYWN0b3JzIjpbeyJ0eXBlIjoicGFzc3dvcmQiLCJkZWxpdmVyeV9tZXRob2QiOiJrbm93bGVkZ2UiLCJsYXN0X2F1dGhlbnRpY2F0ZWRfYXQiOiIyMDI1LTExLTI5VDEwOjU2OjM0WiJ9XSwicm9sZXMiOlsic3R5dGNoX21lbWJlciIsInN0eXRjaF9hZG1pbiJdfSwiaWF0IjoxNzY0NDI3MjE0LCJpc3MiOiJzdHl0Y2guY29tL3Byb2plY3QtbGl2ZS00OGZhNGM1Ni03MjIyLTQ0NzUtOTdjYy02YjFmM2Y3YjhiMDgiLCJuYmYiOjE3NjQ0MjcyMTQsInN1YiI6Im1lbWJlci1saXZlLTVmMTIzN2MyLTZkMTQtNDJmYy1iMmMyLWM3NGViMmI2MjZkYiJ9.K-BfKujInhyPz192GmVgesL3JQ6d_kVqSIIRMLq2hE9nH6lUQN7ash9XPC9_Ou6yQmy4y5FPWFUqqcyXCd-uMhAElr-wvy9ZJBzPyjtPWOnKa27Y9MiC-3DetfMhV2GV_L0sMHYCIw30OWqCPVdRoOypCkAOe_pEqfWJgQFmz5Fej8qqX973rzzHMlF6oNR-ML4zPioOxAQy5Xcl8SfLouOa8b8OItB0vx-p1_jFq1H86t29d3lwk1QRMNjbNlMtWgMmJxiTpotPpbJbsFZ1yKqRxJIsu4D56WHilQ9jS6tzpZpqr2Yefq8dhL12pLOGk7KjXDjSZSDgXW6FW7Q3bg; _dd_s=aid=b9f2a9ff-90f8-4d81-9425-16418f4582dc&rum=1&id=b14d2965-3dea-4716-beef-437d174da36e&created=1764425110196&expire=1764428242621"""


# 示例 1: 只升级计划（如果已有 payment_method_id）
def example_upgrade_only():
    """示例：只调用升级接口"""
    result = upgrade_account_plan(
        stripe_payment_method_id="pm_1SYpLvLhDBkzam9laJ9ZEmoE",  # 从 create_payment_method 获取
        amount=10,
        is_chargeless=False,
        cookies=COOKIE_EXAMPLE,  # 使用你提供的 Cookie
    )
    print(result)


# 示例 2: 完整流程（创建支付方式 + 升级计划）
def example_full_flow():
    """示例：完整的支付流程"""
    result = create_payment_and_upgrade(
        amount=10,
        is_chargeless=False,
        cookies=COOKIE_EXAMPLE,  # 使用你提供的 Cookie
    )
    print(result)


if __name__ == "__main__":
    # 运行示例
    # example_upgrade_only()
    example_full_flow()
