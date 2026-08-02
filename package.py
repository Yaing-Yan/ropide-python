import json


def get_text(file):
    """
    读取文本文件，优先 UTF-8；解码失败时回退 GBK，
    以兼容旧版本在中文 Windows 上写出的 GBK 文件。
    """
    try:
        with open(file, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file, "r", encoding="gbk") as f:
            return f.read()


def get_data(file, func="full"):
    data = json.loads(get_text(file))
    return data if func == "full" else data[func]


def package(context, gadgets, leftaddr, rightaddr, version=100):
    return json.dumps(
        {
            "input": context,
            "gadgets": gadgets,
            "leftStartAddress": leftaddr,
            "rightStartAddress": rightaddr,
            "ideVersion": version,
        },
        ensure_ascii=False,
    )


def divied(data, part):
    pass
