# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
"""nX-U8/100 指令编码表。

本表由 CasioEmuNeo/CasioEmuNeo/emulator/Chipset/CPU.cpp 的 opcode_sources
逐条转写（mask/match 由操作数位域计算：mask = ~(operand_mask<<shift) 累加）。
顺序必须与上游完全一致：dispatch 填充是"先到先得"（FCFS），
`if (opcode_dispatch[px]) continue;` 保证靠前的条目优先。

entry = (mask, match, handler_name, disasm_fmt, extra_words)
可用 tools/import_isa.py 从上游 CPU.cpp 重新生成校验。
"""

TABLE = [
    # ---- Arithmetic ----
    (0xF00F, 0x8001, "add_r_r",   "add r{n}, r{m}", 0),
    (0xF000, 0x1000, "add_r_i",   "add r{n}, #{i8:#04x}", 0),
    (0xF11F, 0xF006, "add_er_er", "add er{n}, er{m}", 0),
    (0xF180, 0xE080, "add_er_i7", "add er{n}, #{i7s}", 0),
    (0xF00F, 0x8006, "addc_r_r",  "addc r{n}, r{m}", 0),
    (0xF000, 0x6000, "addc_r_i",  "addc r{n}, #{i8:#04x}", 0),
    (0xF00F, 0x8002, "and_r_r",   "and r{n}, r{m}", 0),
    (0xF000, 0x2000, "and_r_i",   "and r{n}, #{i8:#04x}", 0),
    (0xF00F, 0x8007, "cmp_r_r",   "cmp r{n}, r{m}", 0),
    (0xF000, 0x7000, "cmp_r_i",   "cmp r{n}, #{i8:#04x}", 0),
    (0xF00F, 0x8005, "cmpc_r_r",  "cmpc r{n}, r{m}", 0),
    (0xF000, 0x5000, "cmpc_r_i",  "cmpc r{n}, #{i8:#04x}", 0),
    (0xF11F, 0xF005, "mov_er_er", "mov er{n}, er{m}", 0),
    (0xF180, 0xE000, "mov_er_i7", "mov er{n}, #{i7:#04x}", 0),
    (0xF00F, 0x8000, "mov_r_r",   "mov r{n}, r{m}", 0),
    (0xF000, 0x0000, "mov_r_i",   "mov r{n}, #{i8:#04x}", 0),
    (0xF00F, 0x8003, "or_r_r",    "or r{n}, r{m}", 0),
    (0xF000, 0x3000, "or_r_i",    "or r{n}, #{i8:#04x}", 0),
    (0xF00F, 0x8004, "xor_r_r",   "xor r{n}, r{m}", 0),
    (0xF000, 0x4000, "xor_r_i",   "xor r{n}, #{i8:#04x}", 0),
    (0xF11F, 0xF007, "cmp_er_er", "cmp er{n}, er{m}", 0),
    (0xF00F, 0x8008, "sub_r_r",   "sub r{n}, r{m}", 0),
    (0xF00F, 0x8009, "subc_r_r",  "subc r{n}, r{m}", 0),
    # ---- Shift ----
    (0xF00F, 0x800A, "sll_r_r",   "sll r{n}, r{m}", 0),
    (0xF08F, 0x900A, "sll_r_i",   "sll r{n}, #{w}", 0),
    (0xF00F, 0x800B, "sllc_r_r",  "sllc r{n}, r{m}", 0),
    (0xF08F, 0x900B, "sllc_r_i",  "sllc r{n}, #{w}", 0),
    (0xF00F, 0x800E, "sra_r_r",   "sra r{n}, r{m}", 0),
    (0xF08F, 0x900E, "sra_r_i",   "sra r{n}, #{w}", 0),
    (0xF00F, 0x800C, "srl_r_r",   "srl r{n}, r{m}", 0),
    (0xF08F, 0x900C, "srl_r_i",   "srl r{n}, #{w}", 0),
    (0xF00F, 0x800D, "srlc_r_r",  "srlc r{n}, r{m}", 0),
    (0xF08F, 0x900D, "srlc_r_i",  "srlc r{n}, #{w}", 0),
    # ---- Load/Store（顺序即优先级，先到先得）----
    (0xF1FF, 0x9032, "l_er_ea",    "l er{n}, [ea]", 0),
    (0xF1FF, 0x9052, "l_er_ea_p",  "l er{n}, [ea+]", 0),
    (0xF11F, 0x9002, "l_er_er",    "l er{n}, [er{m}]", 0),
    (0xF11F, 0xA008, "l_er_d16_er", "l er{n}, {imm16:#06x}[er{m}]", 1),
    (0xF1C0, 0xB000, "l_er_bp",    "l er{n}, {d6}[bp]", 0),
    (0xF1C0, 0xB040, "l_er_fp",    "l er{n}, {d6}[fp]", 0),
    (0xF1FF, 0x9012, "l_er_d",     "l er{n}, {imm16:#06x}", 1),
    (0xF0FF, 0x9030, "l_r_ea",     "l r{n}, [ea]", 0),
    (0xF0FF, 0x9050, "l_r_ea_p",   "l r{n}, [ea+]", 0),
    (0xF01F, 0x9000, "l_r_er",     "l r{n}, [er{m}]", 0),
    (0xF01F, 0x9008, "l_r_d16_er", "l r{n}, {imm16:#06x}[er{m}]", 1),
    (0xF0C0, 0xD000, "l_r_bp",     "l r{n}, {d6}[bp]", 0),
    (0xF0C0, 0xD040, "l_r_fp",     "l r{n}, {d6}[fp]", 0),
    (0xF0FF, 0x9010, "l_r_d",      "l r{n}, {imm16:#06x}", 1),
    (0xF3FF, 0x9034, "l_xr_ea",    "l xr{n}, [ea]", 0),
    (0xF3FF, 0x9054, "l_xr_ea_p",  "l xr{n}, [ea+]", 0),
    (0xF7FF, 0x9036, "l_qr_ea",    "l qr{n}, [ea]", 0),
    (0xF7FF, 0x9056, "l_qr_ea_p",  "l qr{n}, [ea+]", 0),
    (0xF1FF, 0x9033, "st_er_ea",    "st er{n}, [ea]", 0),
    (0xF1FF, 0x9053, "st_er_ea_p",  "st er{n}, [ea+]", 0),
    (0xF11F, 0x9003, "st_er_er",    "st er{n}, [er{m}]", 0),
    (0xF11F, 0xA009, "st_er_d16_er", "st er{n}, {imm16:#06x}[er{m}]", 1),
    (0xF1C0, 0xB080, "st_er_bp",    "st er{n}, {d6}[bp]", 0),
    (0xF1C0, 0xB0C0, "st_er_fp",    "st er{n}, {d6}[fp]", 0),
    (0xF1FF, 0x9013, "st_er_d",     "st er{n}, {imm16:#06x}", 1),
    (0xF0FF, 0x9031, "st_r_ea",     "st r{n}, [ea]", 0),
    (0xF0FF, 0x9051, "st_r_ea_p",   "st r{n}, [ea+]", 0),
    (0xF01F, 0x9001, "st_r_er",     "st r{n}, [er{m}]", 0),
    (0xF01F, 0x9009, "st_r_d16_er", "st r{n}, {imm16:#06x}[er{m}]", 1),
    (0xF0C0, 0xD080, "st_r_bp",     "st r{n}, {d6}[bp]", 0),
    (0xF0C0, 0xD0C0, "st_r_fp",     "st r{n}, {d6}[fp]", 0),
    (0xF0FF, 0x9011, "st_r_d",      "st r{n}, {imm16:#06x}", 1),
    (0xF3FF, 0x9035, "st_xr_ea",    "st xr{n}, [ea]", 0),
    (0xF3FF, 0x9055, "st_xr_ea_p",  "st xr{n}, [ea+]", 0),
    (0xF7FF, 0x9037, "st_qr_ea",    "st qr{n}, [ea]", 0),
    (0xF7FF, 0x9057, "st_qr_ea_p",  "st qr{n}, [ea+]", 0),
    # ---- 控制寄存器 ----
    (0xFF00, 0xE100, "add_sp_i8", "add sp, #{i8s}", 0),
    (0xFF0F, 0xA00F, "mov_ecsr_r", "mov ecsr, r{m}", 0),
    (0xFF1F, 0xA00D, "mov_elr_er", "mov elr, er{m}", 0),
    (0xFF0F, 0xA00C, "mov_epsw_r", "mov epsw, r{m}", 0),
    (0xF1FF, 0xA005, "mov_er_elr", "mov er{n}, elr", 0),
    (0xF1FF, 0xA01A, "mov_er_sp",  "mov er{n}, sp", 0),
    (0xFF0F, 0xA00B, "mov_psw_r",  "mov psw, r{m}", 0),
    (0xFF00, 0xE900, "mov_psw_i",  "mov psw, #{i8:#04x}", 0),
    (0xF0FF, 0xA007, "mov_r_ecsr", "mov r{n}, ecsr", 0),
    (0xF0FF, 0xA004, "mov_r_epsw", "mov r{n}, epsw", 0),
    (0xF0FF, 0xA003, "mov_r_psw",  "mov r{n}, psw", 0),
    (0xFF1F, 0xA10A, "mov_sp_er",  "mov sp, er{m}", 0),
    # ---- PUSH/POP ----
    (0xF1FF, 0xF05E, "push_er", "push er{n}", 0),
    (0xF7FF, 0xF07E, "push_qr", "push qr{n}", 0),
    (0xF0FF, 0xF04E, "push_r",  "push r{n}", 0),
    (0xF3FF, 0xF06E, "push_xr", "push xr{n}", 0),
    (0xF0FF, 0xF0CE, "push_l",  "push {rlist}", 0),
    (0xF1FF, 0xF01E, "pop_er",  "pop er{n}", 0),
    (0xF7FF, 0xF03E, "pop_qr",  "pop qr{n}", 0),
    (0xF0FF, 0xF00E, "pop_r",   "pop r{n}", 0),
    (0xF3FF, 0xF02E, "pop_xr",  "pop xr{n}", 0),
    (0xF0FF, 0xF08E, "pop_l",   "pop {rlist}", 0),
    # ---- 协处理器数据传送 ----
    (0xF00F, 0xA00E, "mov_cr_r",  "mov cr{n}, r{m}", 0),
    (0xF0FF, 0xF00D, "l_cr1_ea",   "l cr{n}, [ea]", 0),
    (0xF0FF, 0xF01D, "l_cr1_ea_p", "l cr{n}, [ea+]", 0),
    (0xF1FF, 0xF02D, "l_cr2_ea",   "l cr{n}, [ea]", 0),
    (0xF1FF, 0xF03D, "l_cr2_ea_p", "l cr{n}, [ea+]", 0),
    (0xF3FF, 0xF04D, "l_cr4_ea",   "l cr{n}, [ea]", 0),
    (0xF3FF, 0xF05D, "l_cr4_ea_p", "l cr{n}, [ea+]", 0),
    (0xF7FF, 0xF06D, "l_cr8_ea",   "l cr{n}, [ea]", 0),
    (0xF7FF, 0xF07D, "l_cr8_ea_p", "l cr{n}, [ea+]", 0),
    (0xF00F, 0xA006, "mov_r_cr",  "mov r{n}, cr{m}", 0),
    (0xF0FF, 0xF08D, "st_cr1_ea",   "st cr{n}, [ea]", 0),
    (0xF0FF, 0xF09D, "st_cr1_ea_p", "st cr{n}, [ea+]", 0),
    (0xF1FF, 0xF0AD, "st_cr2_ea",   "st cr{n}, [ea]", 0),
    (0xF1FF, 0xF0BD, "st_cr2_ea_p", "st cr{n}, [ea+]", 0),
    (0xF3FF, 0xF0CD, "st_cr4_ea",   "st cr{n}, [ea]", 0),
    (0xF3FF, 0xF0DD, "st_cr4_ea_p", "st cr{n}, [ea+]", 0),
    (0xF7FF, 0xF0ED, "st_cr8_ea",   "st cr{n}, [ea]", 0),
    (0xF7FF, 0xF0FD, "st_cr8_ea_p", "st cr{n}, [ea+]", 0),
    # ---- EA ----
    (0xFF1F, 0xF00A, "lea_er",     "lea [er{m}]", 0),
    (0xFF1F, 0xF00B, "lea_d16_er", "lea {imm16:#06x}[er{m}]", 1),
    (0xFFFF, 0xF00C, "lea_d",      "lea {imm16:#06x}", 1),
    # ---- ALU ----
    (0xF0FF, 0x801F, "daa", "daa r{n}", 0),
    (0xF0FF, 0x803F, "das", "das r{n}", 0),
    (0xF0FF, 0x805F, "neg", "neg r{n}", 0),
    # ---- 位操作 ----
    (0xF08F, 0xA000, "sb_r", "sb r{n}.{b}", 0),
    (0xFF8F, 0xA080, "sb_d", "sb {imm16:#06x}.{b}", 1),
    (0xF08F, 0xA002, "rb_r", "rb r{n}.{b}", 0),
    (0xFF8F, 0xA082, "rb_d", "rb {imm16:#06x}.{b}", 1),
    (0xF08F, 0xA001, "tb_r", "tb r{n}.{b}", 0),
    (0xFF8F, 0xA081, "tb_d", "tb {imm16:#06x}.{b}", 1),
    # ---- PSW ----
    (0xFFFF, 0xED08, "ei",   "ei", 0),
    (0xFFFF, 0xEBF7, "di",   "di", 0),
    (0xFFFF, 0xED80, "sc",   "sc", 0),
    (0xFFFF, 0xEB7F, "rc",   "rc", 0),
    (0xFFFF, 0xFECF, "cplc", "cplc", 0),
    # ---- 条件相对分支 ----
    (0xFF00, 0xC000, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC100, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC200, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC300, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC400, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC500, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC600, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC700, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC800, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xC900, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xCA00, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xCB00, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xCC00, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xCD00, "bcond", "b{cond} {target:#06x}", 0),
    (0xFF00, 0xCE00, "bcond", "b{cond} {target:#06x}", 0),
    # ---- 符号扩展 ----
    (0xFFFF, 0x810F, "extbw", "extbw er{m}", 0),
    (0xFFFF, 0x832F, "extbw", "extbw er{m}", 0),
    (0xFFFF, 0x854F, "extbw", "extbw er{m}", 0),
    (0xFFFF, 0x876F, "extbw", "extbw er{m}", 0),
    (0xFFFF, 0x898F, "extbw", "extbw er{m}", 0),
    (0xFFFF, 0x8BAF, "extbw", "extbw er{m}", 0),
    (0xFFFF, 0x8DCF, "extbw", "extbw er{m}", 0),
    (0xFFFF, 0x8FEF, "extbw", "extbw er{m}", 0),
    # ---- 软件中断 ----
    (0xFFC0, 0xE500, "swi", "swi #{sw}", 0),
    (0xFFFF, 0xFFFF, "brk", "brk", 0),
    # ---- 分支 ----
    (0xF0FF, 0xF000, "b_cadr",  "b {seg:x}:{imm16:#06x}", 1),
    (0xFF1F, 0xF002, "b_er",    "b er{m}", 0),
    (0xF0FF, 0xF001, "bl_cadr", "bl {seg:x}:{imm16:#06x}", 1),
    (0xFF1F, 0xF003, "bl_er",   "bl er{m}", 0),
    # ---- 乘除 ----
    (0xF10F, 0xF004, "mul", "mul er{n}, r{m}", 0),
    (0xF10F, 0xF009, "div", "div er{n}, r{m}", 0),
    # ---- misc ----
    (0xFFFF, 0xFE2F, "inc_ea", "inc [ea]", 0),
    (0xFFFF, 0xFE3F, "dec_ea", "dec [ea]", 0),
    (0xFFFF, 0xFE1F, "rt",     "rt", 0),
    (0xFFFF, 0xFE0F, "rti",    "rti", 0),
    (0xFFFF, 0xFE8F, "nop",    "nop", 0),
    (0xFFFF, 0xFE9F, "dsr_dsr", "dsr <- dsr", 0),
    (0xFF00, 0xE300, "dsr_i8",  "dsr <- #{i8:#04x}", 0),
    (0xFF0F, 0x900F, "dsr_r",   "dsr <- r{m}", 0),
]

COND = ["ge", "lt", "gt", "le", "ges", "lts", "gts", "les",
        "ne", "eq", "nv", "ov", "ps", "ns", "al", "al"]


def _iter_matches(mask, match):
    free = [i for i in range(16) if not ((mask >> i) & 1)]
    n = len(free)
    for c in range(1 << n):
        v = match
        for k, bit in enumerate(free):
            if (c >> k) & 1:
                v |= 1 << bit
        yield v


def build_tables(handler_lookup):
    """返回 (dispatch[65536], info[65536])；info = (name, fmt, extra_words)

    与上游一致：按 TABLE 顺序"先到先得"填充，先声明者占位。"""
    dispatch = [None] * 65536
    info = [None] * 65536
    for mask, match, name, fmt, extra in TABLE:
        fn = handler_lookup(name)
        rec = (name, fmt, extra)
        for op in _iter_matches(mask, match):
            if dispatch[op] is None:      # FCFS，先到先得
                dispatch[op] = fn
                info[op] = rec
    return dispatch, info
