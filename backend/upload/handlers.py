"""
上传文件解析处理器映射表。

每个 handler 函数签名: def handler(file_path: str) -> dict
返回: {"success": True/False, "message": "...", "rows": 0}

新增上传类型时，在这里添加 code → handler 映射即可。
"""


def noop_handler(file_path: str) -> dict:
    """占位处理器：文件已保存，暂不支持解析"""
    return {"success": True, "message": "文件已保存，暂不支持自动解析", "rows": 0}


# code → handler 映射表
HANDLERS = {
    # 示例（后续逐步添加解析逻辑）:
    # "performance_data": parse_performance_excel,
    # "payment_data": parse_payment_excel,
}
