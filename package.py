import json


def get_data(file, func="full"):
    with open(file, "r") as f:
        return json.loads(f.read())[func] if func != "full" else json.loads(f.read())


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
