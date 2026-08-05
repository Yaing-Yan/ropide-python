def bp(grid: list[list[int]]) -> str:
    dot_bit = {
        (0, 0): 0,
        (1, 0): 1,
        (2, 0): 2,
        (0, 1): 3,
        (1, 1): 4,
        (2, 1): 5,
        (3, 0): 6,
        (3, 1): 7,
    }
    offset = 0
    for r in range(4):
        for c in range(2):
            if grid[r][c] == 1:
                offset |= 1 << dot_bit[(r, c)]

    return chr(0x2800 + offset)


def rbs(file_path, offset, y):
    """
    :param offset: 偏移量，e.g. 0x00001
    :param y: 读取字节数
    """
    offset = int(offset, 16) if isinstance(offset, str) else offset 
    with open(file_path, "rb") as f:
        f.seek(offset)
        data = f.read(y)
        #if not data:
        #    print("Data Not Found.")
        #    return

    binastr = "".join(f"{b:08b}" for b in data)
    return binastr


while True:
    path = input("enter the file path: ")
    offset = input("enter the offset(start with 0xD000): ")
    y = int(input("how many bytes will you want to read: "))
    print(rbs(path, offset, y))
