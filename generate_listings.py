import json
import random
from datetime import datetime, timedelta

def generate_property_records():
    # 基础数据准备
    landlord_names = [
        "frank", "linda", "elizabeth", "john", "mary", "robert", "jennifer",
        "william", "david", "sarah", "michael", "anna", "richard", "emily",
        "joseph", "sophia", "thomas", "olivia", "daniel", "ava"
    ]
    
    # 起始时间（设置一个合理的起始点，后续按秒递增）
    start_time = datetime(2025, 11, 1, 0, 0, 0)  # 2025-11-01 00:00:00
    
    properties = {}
    
    for i in range(1, 5001):  # 生成A0001到A5000（共5000条）
        # 生成编号（确保4位数字格式，如A0001、A0002...A5000）
        code = f"A{i:04d}"
        
        # 随机生成字段值
        landlord = random.choice(landlord_names)
        # 生成9位数字的邮箱（100000000-999999999）
        landlord_email = f"{random.randint(100000000, 999999999)}@gmail.com"
        monthly_rent = str(random.randint(1, 10000))  # 租金范围1-10000
        area = str(random.randint(1, 200))  # 面积范围1-200平方米
        property_type = random.choice(["Condo", "HDB"])  # 仅两种类型
        rooms = str(random.randint(1, 6))  # 房间数1-6
        # 地址范围010000-289999（确保6位数字，前补0）
        property_address = f"{random.randint(10000, 289999):06d}"
        
        # 时间递增（每次随机增加1-20秒，避免时间重复）
        start_time += timedelta(seconds=random.randint(1, 20))
        last_updated = start_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # 添加到字典
        properties[code] = {
            "landlord_email": landlord_email,
            "landlord": landlord,
            "monthly_rent": monthly_rent,
            "area": area,
            "property_type": property_type,
            "rooms": rooms,
            "property_address": property_address,
            "last_updated": last_updated
        }
    
    # 保存为JSON文件
    with open("property_records_5000.json", "w", encoding="utf-8") as f:
        json.dump(properties, f, indent=2, ensure_ascii=False)
    
    print("生成完成！共5000条记录，已保存到 property_records_5000.json")

if __name__ == "__main__":
    generate_property_records()