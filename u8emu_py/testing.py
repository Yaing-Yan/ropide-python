from u8emu.cnxemu import Cnxemu

cnx = Cnxemu().load(
    "/home/yanshangxuan/models-/fx991cnxfVirtual/rom.bin"
)  # 加载 ROM（默认 fx991cnxf，可指定 model=）
print("load it.")

cnx.press(
    "shift 9 3 = ac ac menu 2 shift menu 1 3 1 shift 8 down 2 7 = up left shift 7 3 nega left left right shift 7 3 nega left 9 del left right shift 7 3 dfm left 9 del del del = right del del 1 2 3 4 5 6 7 0 2 0 0 1 1 right 1 eng sto dfm ac 1 . 0 0 9 6 7 5 0 1 0 0 0 2 9 eng sto ds up up left del del left 1 0 . 0 0 2 9 right 0 0 0 0 0 2 8 1 eng sto sin up up up right del 8 . 9 8 3 9 0 2 4 5 right 6 8 0 right 1 eng sto cos ac 1 0 0 9 2 7 3 0 1 eng sto tan ac down left shift . left left right . left 9 del del down del shift ) shift pf optn 3 alpha jf 2 = ac ac shift menu down down 4 2 "
)
cnx.control(exit_key="q")  # 控制台：默认无说明文字，LCD 从第 1 行原地刷新
print(cnx.showram(0xD180, 16))  # "00 00 ..." 格式读取
cnx.kill()
