# utils/rent_tools.py
"""
租房助手工具模块：
- 租金计算
- 退租日期计算
- 维修责任判断
此文件供房东端与租客端共用。
"""
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from langchain.tools import tool


@tool(return_direct=True)
def calculate_rent(
    monthly_rent: float,
    stay_months: int,
    deposit: float = 0.0,
    is_early_termination: bool = False,
    notice_period_months: int = 2
) -> str:
    """
    计算租房相关的租金和押金金额，支持提前退租的违约金计算。
    """
    total_rent = monthly_rent * stay_months
    if is_early_termination:
        penalty = monthly_rent * notice_period_months
        refundable_deposit = max(0.0, deposit - penalty)
        return (
            f"🏠 租金计算结果：\n"
            f"- 月租金：S${monthly_rent:.2f}\n"
            f"- 实际居住月数：{stay_months}个月\n"
            f"- 应付租金总额：S${total_rent:.2f}\n"
            f"- 提前退租违约金（{notice_period_months}个月通知期）：S${penalty:.2f}\n"
            f"- 已付押金：S${deposit:.2f}\n"
            f"- 可退还押金：S${refundable_deposit:.2f}\n"
            f"⚠️ 注：违约金计算基于常见租房合同条款，具体以您的合同为准。"
        )
    else:
        refundable_deposit = deposit
        return (
            f"🏠 租金计算结果：\n"
            f"- 月租金：S${monthly_rent:.2f}\n"
            f"- 居住月数：{stay_months}个月\n"
            f"- 应付租金总额：S${total_rent:.2f}\n"
            f"- 已付押金：S${deposit:.2f}\n"
            f"- 可退还押金（无损坏情况下）：S${refundable_deposit:.2f}"
        )


@tool(return_direct=True)
def calculate_moveout_date(current_date: str, notice_days: int = 60) -> str:
    """
    根据退租通知日期和通知期，计算退租截止日期。
    例如：current_date="2025-03-01"，notice_days=60。
    """
    try:
        current = datetime.strptime(current_date, "%Y-%m-%d")
        moveout_date = current + timedelta(days=notice_days)
        days_remaining = (moveout_date - current).days
        return (
            f"📅 退租日期计算结果：\n"
            f"- 通知提交日期：{current.strftime('%Y年%m月%d日')}\n"
            f"- 通知期：{notice_days}天\n"
            f"- 退租截止日期：{moveout_date.strftime('%Y年%m月%d日')}\n"
            f"- 剩余天数：{days_remaining}天\n"
            f"✅ 请在截止日前完成退租检查和钥匙交接。"
        )
    except Exception as e:
        return f"❌ 日期计算错误：{str(e)}，请确保日期格式为YYYY-MM-DD（如2025-03-01）"


@tool(return_direct=True)
def get_repair_responsibility(repair_type: str, cost: float = 0.0) -> str:
    """
    判断不同类型维修的责任方（房东或租户）及费用承担规则。
    例如：repair_type="空调"，cost=250。
    """
    repair_type = repair_type.lower()
    if "灯泡" in repair_type or "灯管" in repair_type:
        return f"💡 {repair_type}维修责任：租户承担（需自行更换，费用自付）"

    elif "空调" in repair_type:
        return (
            f"❄️ {repair_type}维修责任：\n"
            f"- 定期保养（每3个月）：房东承担\n"
            f"- 正常损坏（非人为原因）：房东承担\n"
            f"- 使用不当造成损坏：租户承担\n"
            f"⚠️ 具体以合同约定为准。"
        )

    elif cost > 0:
        if cost <= 200:
            return f"💰 {repair_type}维修（S${cost:.2f}）：租户全额承担（小额维修条款）"
        else:
            tenant_share = 200.0
            landlord_share = cost - 200.0
            return (
                f"💰 {repair_type}维修（S${cost:.2f}）：\n"
                f"- 租户承担：S${tenant_share:.2f}\n"
                f"- 房东承担：S${landlord_share:.2f}\n"
                f"⚠️ 通常超过200新元的部分由房东负责。"
            )

    elif any(k in repair_type for k in ["墙面", "屋顶", "水管", "电路", "结构"]):
        return f"🏗️ {repair_type}维修责任：房东承担（属于房屋结构或公共设施）"

    else:
        return f"ℹ️ 暂未明确{repair_type}的维修责任，请参考租房合同条款或提供更多细节。"
