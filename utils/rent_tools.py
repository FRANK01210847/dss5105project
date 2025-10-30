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
            f"🏠 Rent Calculation Result:\n"
            f"- Monthly Rent: S${monthly_rent:.2f}\n"
            f"- Actual Stay Duration: {stay_months} months\n"
            f"- Total Rent Payable: S${total_rent:.2f}\n"
            f"- Early Termination Penalty (Notice Period: {notice_period_months} months): S${penalty:.2f}\n"
            f"- Deposit Paid: S${deposit:.2f}\n"
            f"- Refundable Deposit: S${refundable_deposit:.2f}\n"
            f"⚠️ Note: The penalty calculation is based on common rental contract terms and is subject to your specific contract."
        )
    else:
        refundable_deposit = deposit
        return (
            f"🏠 Rent Calculation Result:\n"
            f"- Monthly Rent: S${monthly_rent:.2f}\n"
            f"- Actual Stay Duration: {stay_months} months\n"
            f"- Total Rent Payable: S${total_rent:.2f}\n"
            f"- Deposit Paid: S${deposit:.2f}\n"
            f"- Refundable Deposit (No Damage): S${refundable_deposit:.2f}"
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
            f"📅 Move-Out Date Calculation Result:\n"
            f"- Notice Submission Date: {current.strftime('%Y年%m月%d日')}\n"
            f"- Notice Period: {notice_days}天\n"
            f"- Move-Out Deadline: {moveout_date.strftime('%Y年%m月%d日')}\n"
            f"- Days Remaining: {days_remaining}天\n"
            f"✅ Please complete the move-out inspection and key handover before the deadline."
        )
    except Exception as e:
        return f"❌ Date Calculation Error: {str(e)}. Please ensure the date format is YYYY-MM-DD (e.g., 2025-03-01)."


@tool(return_direct=True)
def get_repair_responsibility(repair_type: str, cost: float = 0.0) -> str:
    """
    Judge repair responsibility based on repair type and cost.
    For example: repair_type="air conditioner"，cost=250。
    """
    repair_type = repair_type.lower()
    if "bulb" in repair_type or "tube" in repair_type:
        return f"💡 {repair_type} maintenance responsibility: Tenant bears (needs to be replaced by themselves, cost borne by themselves)"

    elif "air conditioner" in repair_type:
        return (
            f"❄️ {repair_type} maintenance responsibility:\n"
            f"- Regular maintenance (every 3 months): Landlord bears\n"
            f"- Normal wear and tear (non-human causes): Landlord bears\n"
            f"- Damage caused by improper use: Tenant bears\n"
            f"⚠️ Subject to specific contract terms."
        )

    elif cost > 0:
        if cost <= 200:
            return f"💰 {repair_type} maintenance (S${cost:.2f}): Tenant bears full responsibility (small repair clause)"
        else:
            tenant_share = 200.0
            landlord_share = cost - 200.0
            return (
                f"💰 {repair_type} maintenance (S${cost:.2f}):\n"
                f"- Tenant bears: S${tenant_share:.2f}\n"
                f"- Landlord bears: S${landlord_share:.2f}\n"
                f"⚠️ Usually, the portion exceeding S$200 is borne by the landlord."
            )

    elif any(k in repair_type for k in ["light", "roof", "pipe", "circuit", "structure"]):
        return f"🏗️ {repair_type} maintenance responsibility: Landlord bears (belongs to building structure or public facilities)"

    else:
        return f"ℹ️ Unable to determine {repair_type} maintenance responsibility, please refer to the rental contract terms or provide more details."
