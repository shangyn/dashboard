"""
上传文件解析处理器映射表。

每个 handler 函数签名: def handler(file_path: str) -> dict
返回: {"success": True/False, "message": "...", "rows": 0}

新增上传类型时，在这里添加 code → handler 映射即可。
"""

from dashboards.contract_completion.handlers import (
    parse_ledger_contracts,
    parse_country_mapping,
    parse_payment_collections,
    parse_report_a,
    parse_report_b,
    parse_trade_data,
    parse_trade_data_2025,
    parse_overseas_diff,
    parse_accessories_payment,
    parse_schedule_tracking,
)


def noop_handler(file_path: str) -> dict:
    """占位处理器：文件已保存，暂不支持解析"""
    return {"success": True, "message": "文件已保存，暂不支持自动解析", "rows": 0}


# code → handler 映射表
HANDLERS = {
    # 合同完成情况表
    "contract_ledger":      parse_ledger_contracts,
    "contract_mapping":     parse_country_mapping,
    "contract_payment":     parse_payment_collections,
    "contract_report_a":    parse_report_a,
    "contract_report_b":    parse_report_b,
    "contract_trade_data":  parse_trade_data,
    "contract_trade_data_2025": parse_trade_data_2025,
    "contract_overseas_diff": parse_overseas_diff,
    "contract_accessories_payment": parse_accessories_payment,
    # 工期统计
    "schedule_data": parse_schedule_tracking,
}
