#!/usr/bin/env python3
"""
disasm16.py — Basic x86-16 disassembler for MTU.EXE (Win16 NE)
Disassembles specific code regions from Seg3 of the executable.

@yasinkuyu
"""

import os
import struct

# ─── Register tables ───────────────────────────────────────────────────────────

REG16 = ['AX', 'CX', 'DX', 'BX', 'SP', 'BP', 'SI', 'DI']
REG8  = ['AL', 'CL', 'DL', 'BL', 'AH', 'CH', 'DH', 'BH']
SEG_REG = ['ES', 'CS', 'SS', 'DS']
SREG_OVERRIDE = {0x26: 'ES', 0x2E: 'CS', 0x36: 'SS', 0x3E: 'DS'}

# ALU operation names for /r field (index 0-7)
# x86 encoding: /0=ADD, /1=OR, /2=ADC, /3=SBB, /4=AND, /5=SUB, /6=XOR, /7=CMP
ALU_ops = ['ADD', 'OR', 'ADC', 'SBB', 'AND', 'SUB', 'XOR', 'CMP']

# ─── ModRM decoding ────────────────────────────────────────────────────────────

def decode_modrm(data, offset, word_size=1):
    """Decode ModRM byte and optional SIB/displacement.
    Returns (operand_str, bytes_consumed, modrm_raw, reg_field, rm_field, mod_field).
    word_size: 1 for 8-bit, 2 for 16-bit.
    """
    if offset >= len(data):
        return '???', 0, 0, 0, 0, 0
    modrm = data[offset]
    mod = (modrm >> 6) & 3
    reg = (modrm >> 3) & 7
    rm  = modrm & 7
    consumed = 1
    ea = ''

    if mod == 3:
        # Register direct
        ea = REG8[rm] if word_size == 1 else REG16[rm]
        return ea, consumed, modrm, reg, rm, mod

    # Memory operands
    if mod == 0:
        if rm == 6:
            # Direct address [disp16]
            disp = struct.unpack('<H', data[offset+1:offset+3])[0]
            consumed += 2
            ea = f'[{disp:04X}h]'
        elif rm == 4:
            # SIB byte present (rare in 16-bit, but possible)
            ea = '[SI+DI]?'  # placeholder
        else:
            base_reg = {
                0: 'BX+SI', 1: 'BX+DI', 2: 'BP+SI', 3: 'BP+DI',
                4: 'SI', 5: 'DI', 6: 'BP', 7: 'BX'
            }[rm]
            ea = f'[{base_reg}]'
    elif mod == 1:
        # [reg + disp8]
        disp = data[offset+1]
        if disp > 127:
            disp = disp - 256
        consumed += 1
        base_reg = {
            0: 'BX+SI', 1: 'BX+DI', 2: 'BP+SI', 3: 'BP+DI',
            4: 'SI', 5: 'DI', 6: 'BP', 7: 'BX'
        }[rm]
        if disp < 0:
            ea = f'[{base_reg}{disp}]'
        elif disp == 0:
            ea = f'[{base_reg}]'
        else:
            ea = f'[{base_reg}+{disp}]'
    elif mod == 2:
        # [reg + disp16]
        disp = struct.unpack('<H', data[offset+1:offset+3])[0]
        consumed += 2
        base_reg = {
            0: 'BX+SI', 1: 'BX+DI', 2: 'BP+SI', 3: 'BP+DI',
            4: 'SI', 5: 'DI', 6: 'BP', 7: 'BX'
        }[rm]
        if disp > 0x7FFF:
            ea = f'[{base_reg}-{0x10000-disp:04X}h]'
        else:
            ea = f'[{base_reg}+{disp:04X}h]'

    return ea, consumed, modrm, reg, rm, mod


def decode_modrm_with_reg(data, offset, word_size, reg_table):
    """Decode ModRM and return reg name + effective address."""
    ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset, word_size)
    reg_name = reg_table[reg]
    return reg_name, ea, consumed, mod, rm


# ─── Instruction disassembly ───────────────────────────────────────────────────

def disasm_instruction(data, offset, seg_base=0, dgroup_base=0):
    """
    Disassemble one x86-16 instruction at data[offset].
    Returns (instruction_text, raw_bytes_count, extra_info).
    extra_info may contain DGROUP references or import thunks.
    """
    start = offset
    extra = ''
    seg_override = None

    # Parse prefixes
    prefixes = []
    while offset < len(data):
        b = data[offset]
        if b in (0x26, 0x2E, 0x36, 0x3E):
            seg_override = SREG_OVERRIDE[b]
            prefixes.append(b)
            offset += 1
        elif b == 0xF0:
            prefixes.append(b)
            offset += 1  # LOCK
        elif b == 0xF2:
            prefixes.append(b)
            offset += 1  # REPNE
        elif b == 0xF3:
            prefixes.append(b)
            offset += 1  # REPE/REPZ
        elif b == 0x2E:
            prefixes.append(b)
            offset += 1
        elif b == 0x66:
            prefixes.append(b)
            offset += 1  # operand size override
        elif b == 0x67:
            prefixes.append(b)
            offset += 1  # address size override
        else:
            break

    if offset >= len(data):
        return 'DB ??', 1, ''

    b = data[offset]
    prefix_len = offset - start  # number of prefix bytes consumed
    raw_len = prefix_len + 1  # at least 1 byte (the opcode)

    # ── PUSH segment register (06=ES, 0E=CS, 16=SS, 1E=DS) ──
    if b == 0x06: return 'PUSH ES', raw_len, extra
    if b == 0x0E: return 'PUSH CS', raw_len, extra
    if b == 0x16: return 'PUSH SS', raw_len, extra
    if b == 0x1E: return 'PUSH DS', raw_len, extra

    # ── POP segment register (07=ES, 0F=CS reserved, 17=SS, 1F=DS) ──
    if b == 0x07: return 'POP ES', raw_len, extra
    if b == 0x17: return 'POP SS', raw_len, extra
    if b == 0x1F: return 'POP DS', raw_len, extra

    # ── DAA/DAS/AAA/AAS (27/2F/37/3F) ──
    if b == 0x27: return 'DAA', raw_len, extra
    if b == 0x2F: return 'DAS', raw_len, extra
    if b == 0x37: return 'AAA', raw_len, extra
    if b == 0x3F: return 'AAS', raw_len, extra

    # ── ADD AX, imm16 (05) ──
    if b == 0x05:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'ADD AX, {imm:04X}h', raw_len, extra
        else:
            return 'ADD AX, ???', raw_len, extra

    # ── OR AX, imm16 (0D) ──
    if b == 0x0D:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'OR AX, {imm:04X}h', raw_len, extra
        else:
            return 'OR AX, ???', raw_len, extra

    # ── ADC AX, imm16 (15) ──
    if b == 0x15:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'ADC AX, {imm:04X}h', raw_len, extra
        else:
            return 'ADC AX, ???', raw_len, extra

    # ── SBB AX, imm16 (1D) ──
    if b == 0x1D:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'SBB AX, {imm:04X}h', raw_len, extra
        else:
            return 'SBB AX, ???', raw_len, extra

    # ── AND AX, imm16 (25) ──
    if b == 0x25:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'AND AX, {imm:04X}h', raw_len, extra
        else:
            return 'AND AX, ???', raw_len, extra

    # ── SUB AX, imm16 (2D) ──
    if b == 0x2D:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'SUB AX, {imm:04X}h', raw_len, extra
        else:
            return 'SUB AX, ???', raw_len, extra

    # ── XOR AX, imm16 (35) ──
    if b == 0x35:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'XOR AX, {imm:04X}h', raw_len, extra
        else:
            return 'XOR AX, ???', raw_len, extra

    # ── NOP ──
    if b == 0x90:
        prefix_str = ''
        if seg_override:
            prefix_str = f'{seg_override}:'
        return f'{prefix_str}NOP', raw_len, extra

    # ── HLT ──
    if b == 0xF4:
        return 'HLT', raw_len, extra

    # ── CLC / STC / CLI / STI / CLD / STD ──
    if b == 0xF8: return 'CLC', raw_len, extra
    if b == 0xF9: return 'STC', raw_len, extra
    if b == 0xFA: return 'CLI', raw_len, extra
    if b == 0xFB: return 'STI', raw_len, extra
    if b == 0xFC: return 'CLD', raw_len, extra
    if b == 0xFD: return 'STD', raw_len, extra

    # ── PUSH r16 (50-57) ──
    if 0x50 <= b <= 0x57:
        return f'PUSH {REG16[b-0x50]}', raw_len, extra

    # ── POP r16 (58-5F) ──
    if 0x58 <= b <= 0x5F:
        return f'POP {REG16[b-0x58]}', raw_len, extra

    # ── INC r16 (40-47) ──
    if 0x40 <= b <= 0x47:
        return f'INC {REG16[b-0x40]}', raw_len, extra

    # ── DEC r16 (48-4F) ──
    if 0x48 <= b <= 0x4F:
        return f'DEC {REG16[b-0x48]}', raw_len, extra

    # ── MOV r16, imm16 (B8-BF) ──
    if 0xB8 <= b <= 0xBF:
        reg = REG16[b - 0xB8]
        if offset + 2 <= len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            # DGROUP check
            if reg == 'BP' and 0x9000 <= imm <= 0xB000:
                extra = f'; DGROUP+{imm-dgroup_base:04X}h' if dgroup_base else ''
            return f'MOV {reg}, {imm:04X}h', raw_len, extra
        else:
            return f'MOV {reg}, ???', raw_len, extra

    # ── MOV r8, imm8 (B0-B7) ──
    if 0xB0 <= b <= 0xB7:
        reg = REG8[b - 0xB0]
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'MOV {reg}, {imm:02X}h', raw_len, extra
        else:
            return f'MOV {reg}, ???', raw_len, extra

    # ── MOV r/m16, r16 (89) ──
    if b == 0x89:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        reg_name = REG16[reg]
        raw_len = prefix_len + 1 + consumed
        prefix_str = f'{seg_override} ' if seg_override else ''
        return f'MOV {prefix_str}{ea}, {reg_name}', raw_len, extra

    # ── MOV r16, r/m16 (8B) ──
    if b == 0x8B:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        reg_name = REG16[reg]
        raw_len = prefix_len + 1 + consumed
        prefix_str = f'{seg_override} ' if seg_override else ''
        # DGROUP reference
        if mod in (1, 2) and rm == 6:  # BP-based
            if 'BP+' in ea or 'BP-' in ea or ea == '[BP]':
                extra = f'; DGROUP ref'
        return f'MOV {reg_name}, {prefix_str}{ea}', raw_len, extra

    # ── MOV r/m8, r8 (88) ──
    if b == 0x88:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 1)
        reg_name = REG8[reg]
        raw_len = prefix_len + 1 + consumed
        prefix_str = f'{seg_override} ' if seg_override else ''
        return f'MOV {prefix_str}{ea}, {reg_name}', raw_len, extra

    # ── MOV r8, r/m8 (8A) ──
    if b == 0x8A:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 1)
        reg_name = REG8[reg]
        raw_len = prefix_len + 1 + consumed
        prefix_str = f'{seg_override} ' if seg_override else ''
        return f'MOV {reg_name}, {prefix_str}{ea}', raw_len, extra

    # ── MOV AL, [addr] (A0) ──
    if b == 0xA0:
        if offset + 3 <= len(data):
            addr = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            prefix_str = f'{seg_override} ' if seg_override else ''
            return f'MOV AL, {prefix_str}[{addr:04X}h]', raw_len, extra
        else:
            return 'MOV AL, [???]', raw_len, extra

    # ── MOV AX, [addr] (A1) ──
    if b == 0xA1:
        if offset + 3 <= len(data):
            addr = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            prefix_str = f'{seg_override} ' if seg_override else ''
            return f'MOV AX, {prefix_str}[{addr:04X}h]', raw_len, extra
        else:
            return 'MOV AX, [???]', raw_len, extra

    # ── MOV [addr], AL (A2) ──
    if b == 0xA2:
        if offset + 3 <= len(data):
            addr = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            prefix_str = f'{seg_override} ' if seg_override else ''
            return f'MOV {prefix_str}[{addr:04X}h], AL', raw_len, extra
        else:
            return 'MOV [???], AL', raw_len, extra

    # ── MOV [addr], AX (A3) ──
    if b == 0xA3:
        if offset + 3 <= len(data):
            addr = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            prefix_str = f'{seg_override} ' if seg_override else ''
            return f'MOV {prefix_str}[{addr:04X}h], AX', raw_len, extra
        else:
            return 'MOV [???], AX', raw_len, extra

    # ── MOV r/m16, imm16 (C7 /0) ──
    if b == 0xC7:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        if reg == 0:  # /0 = MOV r/m, imm
            imm_offset = offset + 1 + consumed
            if imm_offset + 2 <= len(data):
                imm = struct.unpack('<H', data[imm_offset:imm_offset+2])[0]
                raw_len = prefix_len + 1 + consumed + 2
                return f'MOV {ea}, {imm:04X}h', raw_len, extra
            else:
                return f'MOV {ea}, ???', raw_len, extra
        else:
            return f'???, modrm={modrm:02X}h', raw_len, extra

    # ── MOV r/m8, imm8 (C6 /0) ──
    if b == 0xC6:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 1)
        if reg == 0:
            imm_offset = offset + 1 + consumed
            if imm_offset + 1 <= len(data):
                imm = data[imm_offset]
                raw_len = prefix_len + 1 + consumed + 1
                return f'MOV {ea}, {imm:02X}h', raw_len, extra
            else:
                return f'MOV {ea}, ???', raw_len, extra
        else:
            return f'???, modrm={modrm:02X}h', raw_len, extra

    # ── XCHG AX, r16 (91-97) ──
    if 0x91 <= b <= 0x97:
        return f'XCHG AX, {REG16[b-0x90]}', raw_len, extra

    # ── XCHG r/m8, r8 (86) ──
    if b == 0x86:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 1)
        reg_name = REG8[reg]
        raw_len = prefix_len + 1 + consumed
        return f'XCHG {ea}, {reg_name}', raw_len, extra

    # ── XCHG r/m16, r16 (87) ──
    if b == 0x87:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        reg_name = REG16[reg]
        raw_len = prefix_len + 1 + consumed
        return f'XCHG {ea}, {reg_name}', raw_len, extra

    # ── LEA r16, m (8D) ──
    if b == 0x8D:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        reg_name = REG16[reg]
        raw_len = prefix_len + 1 + consumed
        return f'LEA {reg_name}, {ea}', raw_len, extra

    # ── ADD/ADC/SUB/SBB/CMP/AND/OR/XOR r/m16, r16 (01-03, 09-0B, 11-13, ...) ──
    # Encoding: opcode = (ALU_op * 8) + (direction_bit) + (word_bit)
    # direction: 0 = r/m, r; 1 = r, r/m
    # word: 0 = 8-bit, 1 = 16-bit
    alu_ops_add_sub = {
        0x00: ('ADD', 1, 0), 0x01: ('ADD', 0, 1), 0x02: ('ADD', 1, 0), 0x03: ('ADD', 0, 1),
        0x08: ('OR',  1, 0), 0x09: ('OR',  0, 1), 0x0A: ('OR',  1, 0), 0x0B: ('OR',  0, 1),
        0x10: ('ADC', 1, 0), 0x11: ('ADC', 0, 1), 0x12: ('ADC', 1, 0), 0x13: ('ADC', 0, 1),
        0x18: ('SBB', 1, 0), 0x19: ('SBB', 0, 1), 0x1A: ('SBB', 1, 0), 0x1B: ('SBB', 0, 1),
        0x20: ('AND', 1, 0), 0x21: ('AND', 0, 1), 0x22: ('AND', 1, 0), 0x23: ('AND', 0, 1),
        0x28: ('SUB', 1, 0), 0x29: ('SUB', 0, 1), 0x2A: ('SUB', 1, 0), 0x2B: ('SUB', 0, 1),
        0x30: ('XOR', 1, 0), 0x31: ('XOR', 0, 1), 0x32: ('XOR', 1, 0), 0x33: ('XOR', 0, 1),
        0x38: ('CMP', 1, 0), 0x39: ('CMP', 0, 1), 0x3A: ('CMP', 1, 0), 0x3B: ('CMP', 0, 1),
    }
    if b in alu_ops_add_sub:
        op_name, dir_bit, word_bit = alu_ops_add_sub[b]
        word_size = 2 if word_bit else 1
        reg_table = REG16 if word_size == 2 else REG8
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, word_size)
        reg_name = reg_table[reg]
        raw_len = prefix_len + 1 + consumed
        if dir_bit == 0:
            # r/m, r
            return f'{op_name} {ea}, {reg_name}', raw_len, extra
        else:
            # r, r/m
            return f'{op_name} {reg_name}, {ea}', raw_len, extra

    # ── ADD/ADC/SUB/SBB/CMP/AND/OR/XOR r/m16, imm16 (81) ──
    # and signed imm8 (83)
    if b == 0x81:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        imm_offset = offset + 1 + consumed
        if imm_offset + 2 <= len(data):
            imm = struct.unpack('<H', data[imm_offset:imm_offset+2])[0]
            raw_len = prefix_len + 1 + consumed + 2
            op_name = ALU_ops[reg]
            return f'{op_name} {ea}, {imm:04X}h', raw_len, extra
        else:
            return f'???, modrm={modrm:02X}h', raw_len, extra

    if b == 0x83:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        imm_offset = offset + 1 + consumed
        if imm_offset + 1 <= len(data):
            imm = data[imm_offset]
            if imm > 127:
                imm = imm - 256
            raw_len = prefix_len + 1 + consumed + 1
            op_name = ALU_ops[reg]
            if imm < 0:
                return f'{op_name} {ea}, -{-imm:02X}h', raw_len, extra
            else:
                return f'{op_name} {ea}, {imm:02X}h', raw_len, extra
        else:
            return f'???, modrm={modrm:02X}h', raw_len, extra

    # ── ADD AL, imm8 (04) ──
    if b == 0x04:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'ADD AL, {imm:02X}h', raw_len, extra
        else:
            return 'ADD AL, ???', raw_len, extra

    # ── OR AL, imm8 (0C) ──
    if b == 0x0C:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'OR AL, {imm:02X}h', raw_len, extra
        else:
            return 'OR AL, ???', raw_len, extra

    # ── ADC AL, imm8 (14) ──
    if b == 0x14:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'ADC AL, {imm:02X}h', raw_len, extra
        else:
            return 'ADC AL, ???', raw_len, extra

    # ── SBB AL, imm8 (1C) ──
    if b == 0x1C:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'SBB AL, {imm:02X}h', raw_len, extra
        else:
            return 'SBB AL, ???', raw_len, extra

    # ── AND AL, imm8 (24) ──
    if b == 0x24:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'AND AL, {imm:02X}h', raw_len, extra
        else:
            return 'AND AL, ???', raw_len, extra

    # ── SUB AL, imm8 (2C) ──
    if b == 0x2C:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'SUB AL, {imm:02X}h', raw_len, extra
        else:
            return 'SUB AL, ???', raw_len, extra

    # ── XOR AL, imm8 (34) ──
    if b == 0x34:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'XOR AL, {imm:02X}h', raw_len, extra
        else:
            return 'XOR AL, ???', raw_len, extra

    # ── CMP AL, imm8 (3C) ──
    if b == 0x3C:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'CMP AL, {imm:02X}h', raw_len, extra
        else:
            return 'CMP AL, ???', raw_len, extra

    # ── CMP AX, imm16 (3D) ──
    if b == 0x3D:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'CMP AX, {imm:04X}h', raw_len, extra
        else:
            return 'CMP AX, ???', raw_len, extra

    # ── TEST r/m16, r16 (85) ──
    if b == 0x85:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        reg_name = REG16[reg]
        raw_len = prefix_len + 1 + consumed
        return f'TEST {ea}, {reg_name}', raw_len, extra

    # ── TEST r/m8, r8 (84) ──
    if b == 0x84:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 1)
        reg_name = REG8[reg]
        raw_len = prefix_len + 1 + consumed
        return f'TEST {ea}, {reg_name}', raw_len, extra

    # ── TEST AL, imm8 (A8) ──
    if b == 0xA8:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'TEST AL, {imm:02X}h', raw_len, extra
        else:
            return 'TEST AL, ???', raw_len, extra

    # ── TEST AX, imm16 (A9) ──
    if b == 0xA9:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'TEST AX, {imm:04X}h', raw_len, extra
        else:
            return 'TEST AX, ???', raw_len, extra

    # ── SHL/SHR/SAR/ROL/ROR/RCL/RCR r/m16, 1 or CL ──
    # D0/D1: shift by 1, D2/D3: shift by CL
    # C0/C1: shift by imm8
    shift_ops = ['ROL', 'ROR', 'RCL', 'RCR', 'SHL', 'SHR', 'SAL', 'SAR']

    if b in (0xD0, 0xD1, 0xD2, 0xD3, 0xC0, 0xC1):
        word_size = 2 if b in (0xD1, 0xD3, 0xC1) else 1
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, word_size)
        op_name = shift_ops[reg]
        raw_len = prefix_len + 1 + consumed

        if b in (0xD0, 0xD1):
            return f'{op_name} {ea}, 1', raw_len, extra
        elif b in (0xD2, 0xD3):
            return f'{op_name} {ea}, CL', raw_len, extra
        elif b in (0xC0, 0xC1):
            imm_offset = offset + 1 + consumed
            if imm_offset < len(data):
                imm = data[imm_offset]
                raw_len += 1
                return f'{op_name} {ea}, {imm:02X}h', raw_len, extra
            else:
                return f'{op_name} {ea}, ???', raw_len, extra

    # ── IMUL r/m16 (F7 /5) ──
    if b == 0xF7:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        raw_len = prefix_len + 1 + consumed
        if reg == 5:
            return f'IMUL {ea}', raw_len, extra
        elif reg == 4:
            return f'MUL {ea}', raw_len, extra
        elif reg == 6:
            return f'DIV {ea}', raw_len, extra
        elif reg == 7:
            return f'IDIV {ea}', raw_len, extra
        elif reg == 0:
            # TEST r/m, imm16
            imm_offset = offset + 1 + consumed
            if imm_offset + 2 <= len(data):
                imm = struct.unpack('<H', data[imm_offset:imm_offset+2])[0]
                raw_len += 2
                return f'TEST {ea}, {imm:04X}h', raw_len, extra
        elif reg == 2:
            return f'NOT {ea}', raw_len, extra
        elif reg == 3:
            return f'NEG {ea}', raw_len, extra
        else:
            return f'F7 /{reg} {ea}', raw_len, extra

    # ── IMUL r/m8 (F6 /5) ──
    if b == 0xF6:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 1)
        raw_len = prefix_len + 1 + consumed
        if reg == 5:
            return f'IMUL {ea}', raw_len, extra
        elif reg == 4:
            return f'MUL {ea}', raw_len, extra
        elif reg == 6:
            return f'DIV {ea}', raw_len, extra
        elif reg == 7:
            return f'IDIV {ea}', raw_len, extra
        elif reg == 0:
            imm_offset = offset + 1 + consumed
            if imm_offset + 1 <= len(data):
                imm = data[imm_offset]
                raw_len += 1
                return f'TEST {ea}, {imm:02X}h', raw_len, extra
        elif reg == 2:
            return f'NOT {ea}', raw_len, extra
        elif reg == 3:
            return f'NEG {ea}', raw_len, extra
        else:
            return f'F6 /{reg} {ea}', raw_len, extra

    # ── IMUL r16, r/m16, imm16 (69) ──
    if b == 0x69:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        imm_offset = offset + 1 + consumed
        if imm_offset + 2 <= len(data):
            imm = struct.unpack('<H', data[imm_offset:imm_offset+2])[0]
            raw_len = prefix_len + 1 + consumed + 2
            reg_name = REG16[reg]
            return f'IMUL {reg_name}, {ea}, {imm:04X}h', raw_len, extra
        else:
            return f'IMUL ???', raw_len, extra

    # ── IMUL r16, r/m16, imm8 (6B) ──
    if b == 0x6B:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        imm_offset = offset + 1 + consumed
        if imm_offset + 1 <= len(data):
            imm = data[imm_offset]
            if imm > 127:
                imm = imm - 256
            raw_len = prefix_len + 1 + consumed + 1
            reg_name = REG16[reg]
            if imm < 0:
                return f'IMUL {reg_name}, {ea}, -{-imm:02X}h', raw_len, extra
            else:
                return f'IMUL {reg_name}, {ea}, {imm:02X}h', raw_len, extra
        else:
            return f'IMUL ???', raw_len, extra

    # ── MOVS/B (A4/A5) ──
    if b == 0xA4:
        return 'MOVSB', raw_len, extra
    if b == 0xA5:
        return 'MOVSW', raw_len, extra

    # ── CMPSB/CMPSW (A6/A7) ──
    if b == 0xA6:
        return 'CMPSB', raw_len, extra
    if b == 0xA7:
        return 'CMPSW', raw_len, extra

    # ── STOSB/STOSW (AA/AB) ──
    if b == 0xAA:
        return 'STOSB', raw_len, extra
    if b == 0xAB:
        return 'STOSW', raw_len, extra

    # ── LODSB/LODSW (AC/AD) ──
    if b == 0xAC:
        return 'LODSB', raw_len, extra
    if b == 0xAD:
        return 'LODSW', raw_len, extra

    # ── SCASB/SCASW (AE/AF) ──
    if b == 0xAE:
        return 'SCASB', raw_len, extra
    if b == 0xAF:
        return 'SCASW', raw_len, extra

    # ── PUSH imm16 (68) ──
    if b == 0x68:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'PUSH {imm:04X}h', raw_len, extra
        else:
            return 'PUSH ???', raw_len, extra

    # ── PUSH imm8 (6A) ──
    if b == 0x6A:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            return f'PUSH {imm:02X}h', raw_len, extra
        else:
            return 'PUSH ???', raw_len, extra

    # ── JMP near rel16 (E9) ──
    if b == 0xE9:
        if offset + 2 < len(data):
            rel = struct.unpack('<h', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            target = offset + raw_len + rel
            extra = f'; target file+{target:04X}h'
            return f'JMP SHORT +{rel:04X}h', raw_len, extra
        else:
            return 'JMP ???', raw_len, extra

    # ── JMP short rel8 (EB) ──
    if b == 0xEB:
        if offset + 1 < len(data):
            rel = data[offset+1]
            if rel > 127:
                rel = rel - 256
            raw_len = prefix_len + 2
            target = offset + raw_len + rel
            sign = '+' if rel >= 0 else ''
            extra = f'; target file+{target:04X}h'
            return f'JMP SHORT {sign}{rel:02X}h', raw_len, extra
        else:
            return 'JMP SHORT ???', raw_len, extra

    # ── JMP far ptr (EA) ──
    if b == 0xEA:
        if offset + 4 < len(data):
            off = struct.unpack('<H', data[offset+1:offset+3])[0]
            seg = struct.unpack('<H', data[offset+3:offset+5])[0]
            raw_len = prefix_len + 5
            if seg == 0 and off == 0xFFFF:
                extra = '; IMPORT THUNK (0000:FFFF)'
            else:
                extra = f'; target {seg:04X}:{off:04X}'
            return f'JMP FAR {seg:04X}:{off:04X}', raw_len, extra
        else:
            return 'JMP FAR ???', raw_len, extra

    # ── Jcc short (70-7F) ──
    cc_names = ['JO','JNO','JB','JNB','JZ','JNZ','JBE','JNBE',
                'JS','JNS','JP','JNP','JL','JNL','JLE','JNLE']
    if 0x70 <= b <= 0x7F:
        cc = b - 0x70
        if offset + 1 < len(data):
            rel = data[offset+1]
            if rel > 127:
                rel = rel - 256
            raw_len = prefix_len + 2
            target = offset + raw_len + rel
            sign = '+' if rel >= 0 else ''
            extra = f'; target file+{target:04X}h'
            return f'{cc_names[cc]} SHORT {sign}{rel:02X}h', raw_len, extra
        else:
            return f'{cc_names[cc]} SHORT ???', raw_len, extra

    # ── Jcc near (0F 80-8F) ──
    if b == 0x0F and offset + 1 < len(data):
        b2 = data[offset+1]
        if 0x80 <= b2 <= 0x8F:
            cc = b2 - 0x80
            if offset + 3 < len(data):
                rel = struct.unpack('<h', data[offset+2:offset+4])[0]
                raw_len = prefix_len + 4
                target = offset + raw_len + rel
                sign = '+' if rel >= 0 else ''
                extra = f'; target file+{target:04X}h'
                return f'{cc_names[cc]} NEAR {sign}{rel:04X}h', raw_len, extra
            else:
                return f'{cc_names[cc]} NEAR ???', raw_len, extra

    # ── LOOP/LOOPE/LOOPNE (E0-E2) ──
    if b == 0xE0:
        if offset + 1 < len(data):
            rel = data[offset+1]
            if rel > 127:
                rel = rel - 256
            raw_len = prefix_len + 2
            target = offset + raw_len + rel
            sign = '+' if rel >= 0 else ''
            extra = f'; target file+{target:04X}h'
            return f'LOOPNE {sign}{rel:02X}h', raw_len, extra
        else:
            return 'LOOPNE ???', raw_len, extra
    if b == 0xE1:
        if offset + 1 < len(data):
            rel = data[offset+1]
            if rel > 127:
                rel = rel - 256
            raw_len = prefix_len + 2
            target = offset + raw_len + rel
            sign = '+' if rel >= 0 else ''
            extra = f'; target file+{target:04X}h'
            return f'LOOPE {sign}{rel:02X}h', raw_len, extra
        else:
            return 'LOOPE ???', raw_len, extra
    if b == 0xE2:
        if offset + 1 < len(data):
            rel = data[offset+1]
            if rel > 127:
                rel = rel - 256
            raw_len = prefix_len + 2
            target = offset + raw_len + rel
            sign = '+' if rel >= 0 else ''
            extra = f'; target file+{target:04X}h'
            return f'LOOP {sign}{rel:02X}h', raw_len, extra
        else:
            return 'LOOP ???', raw_len, extra

    # ── CALL rel16 (E8) ──
    if b == 0xE8:
        if offset + 2 < len(data):
            rel = struct.unpack('<h', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            target = offset + raw_len + rel
            sign = '+' if rel >= 0 else ''
            extra = f'; target file+{target:04X}h'
            return f'CALL {sign}{rel:04X}h', raw_len, extra
        else:
            return 'CALL ???', raw_len, extra

    # ── CALL far ptr (9A) ──
    if b == 0x9A:
        if offset + 4 < len(data):
            off = struct.unpack('<H', data[offset+1:offset+3])[0]
            seg = struct.unpack('<H', data[offset+3:offset+5])[0]
            raw_len = prefix_len + 5
            if seg == 0 and off == 0xFFFF:
                extra = '; IMPORT THUNK (0000:FFFF)'
            else:
                extra = f'; call {seg:04X}:{off:04X}'
            return f'CALL FAR {seg:04X}:{off:04X}', raw_len, extra
        else:
            return 'CALL FAR ???', raw_len, extra

    # ── RET near (C3) ──
    if b == 0xC3:
        return 'RET', raw_len, extra

    # ── RETF (CB) ──
    if b == 0xCB:
        return 'RETF', raw_len, extra

    # ── RET imm16 (C2) ──
    if b == 0xC2:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'RET {imm:04X}h', raw_len, extra
        else:
            return 'RET ???', raw_len, extra

    # ── RETF imm16 (CA) ──
    if b == 0xCA:
        if offset + 2 < len(data):
            imm = struct.unpack('<H', data[offset+1:offset+3])[0]
            raw_len = prefix_len + 3
            return f'RETF {imm:04X}h', raw_len, extra
        else:
            return 'RETF ???', raw_len, extra

    # ── INT 3 (CC) ──
    if b == 0xCC:
        return 'INT 3', raw_len, extra

    # ── INT imm8 (CD) ──
    if b == 0xCD:
        if offset + 1 < len(data):
            int_num = data[offset+1]
            raw_len = prefix_len + 2
            return f'INT {int_num:02X}h', raw_len, extra
        else:
            return 'INT ???', raw_len, extra

    # ── IRET (CF) ──
    if b == 0xCF:
        return 'IRET', raw_len, extra

    # ── XLAT (D7) ──
    if b == 0xD7:
        return 'XLAT', raw_len, extra

    # ── IN AL, imm8 (E4) ──
    if b == 0xE4:
        if offset + 1 < len(data):
            port = data[offset+1]
            raw_len = prefix_len + 2
            return f'IN AL, {port:02X}h', raw_len, extra
        else:
            return 'IN AL, ???', raw_len, extra

    # ── IN AX, imm8 (E5) ──
    if b == 0xE5:
        if offset + 1 < len(data):
            port = data[offset+1]
            raw_len = prefix_len + 2
            return f'IN AX, {port:02X}h', raw_len, extra
        else:
            return 'IN AX, ???', raw_len, extra

    # ── OUT imm8, AL (E6) ──
    if b == 0xE6:
        if offset + 1 < len(data):
            port = data[offset+1]
            raw_len = prefix_len + 2
            return f'OUT {port:02X}h, AL', raw_len, extra
        else:
            return 'OUT ???, AL', raw_len, extra

    # ── OUT imm8, AX (E7) ──
    if b == 0xE7:
        if offset + 1 < len(data):
            port = data[offset+1]
            raw_len = prefix_len + 2
            return f'OUT {port:02X}h, AX', raw_len, extra
        else:
            return 'OUT ???, AX', raw_len, extra

    # ── IN AL, DX (EC) ──
    if b == 0xEC:
        return 'IN AL, DX', raw_len, extra

    # ── IN AX, DX (ED) ──
    if b == 0xED:
        return 'IN AX, DX', raw_len, extra

    # ── OUT DX, AL (EE) ──
    if b == 0xEE:
        return 'OUT DX, AL', raw_len, extra

    # ── OUT DX, AX (EF) ──
    if b == 0xEF:
        return 'OUT DX, AX', raw_len, extra

    # ── ENTER (C8) ──
    if b == 0xC8:
        if offset + 3 < len(data):
            alloc = struct.unpack('<H', data[offset+1:offset+3])[0]
            level = data[offset+3]
            raw_len = prefix_len + 4
            return f'ENTER {alloc:04X}h, {level:02X}h', raw_len, extra
        else:
            return 'ENTER ???', raw_len, extra

    # ── LEAVE (C9) ──
    if b == 0xC9:
        return 'LEAVE', raw_len, extra

    # ── PUSH/PUSHA/POPA ──
    if b == 0x60: return 'PUSHA', raw_len, extra
    if b == 0x61: return 'POPA', raw_len, extra

    # ── CBW (98) ──
    if b == 0x98: return 'CBW', raw_len, extra

    # ── CWD (99) ──
    if b == 0x99: return 'CWD', raw_len, extra

    # ── DAA/DAS/AAS/AAM/AAD ──
    if b == 0x27: return 'DAA', raw_len, extra
    if b == 0x2F: return 'DAS', raw_len, extra
    if b == 0x37: return 'AAS', raw_len, extra

    # ── MUL r/m16 (F7 /4) — already covered above ──

    # ── Group 1: /2 = NOT, /3 = NEG, /4 = MUL, /5 = IMUL, /6 = DIV, /7 = IDIV ──
    # Handled in F6/F7 above

    # ── MOV Sreg, r/m16 (8E /r) ──
    if b == 0x8E:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        sreg_name = SEG_REG[reg] if reg < 4 else f'SEG{reg}'
        raw_len = prefix_len + 1 + consumed
        return f'MOV {sreg_name}, {ea}', raw_len, extra

    # ── MOV r/m16, Sreg (8C /r) ──
    if b == 0x8C:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        sreg_name = SEG_REG[reg] if reg < 4 else f'SEG{reg}'
        raw_len = prefix_len + 1 + consumed
        prefix_str = f'{seg_override} ' if seg_override else ''
        return f'MOV {prefix_str}{ea}, {sreg_name}', raw_len, extra

    # ── LES r16, m16:16 (C4) ──
    if b == 0xC4:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        reg_name = REG16[reg]
        raw_len = prefix_len + 1 + consumed
        return f'LES {reg_name}, {ea}', raw_len, extra

    # ── LDS r16, m16:16 (C5) ──
    if b == 0xC5:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        reg_name = REG16[reg]
        raw_len = prefix_len + 1 + consumed
        return f'LDS {reg_name}, {ea}', raw_len, extra

    # ── MOV r/m8, imm8 (80 /r) — ALU r/m8, imm8 ──
    if b == 0x80:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 1)
        imm_offset = offset + 1 + consumed
        if imm_offset + 1 <= len(data):
            imm = data[imm_offset]
            raw_len = prefix_len + 1 + consumed + 1
            op_name = ALU_ops[reg]
            return f'{op_name} {ea}, {imm:02X}h', raw_len, extra
        else:
            return f'???, modrm={modrm:02X}h', raw_len, extra

    # ── INC/DEC r/m8 (FE /0 or /1) ──
    if b == 0xFE:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 1)
        raw_len = prefix_len + 1 + consumed
        if reg == 0:
            return f'INC {ea}', raw_len, extra
        elif reg == 1:
            return f'DEC {ea}', raw_len, extra
        else:
            return f'FE /{reg} {ea}', raw_len, extra

    # ── INC/DEC/CALL/JMP/PUSH r/m16 (FF /r) ──
    if b == 0xFF:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        raw_len = prefix_len + 1 + consumed
        if reg == 0:
            return f'INC WORD {ea}', raw_len, extra
        elif reg == 1:
            return f'DEC WORD {ea}', raw_len, extra
        elif reg == 2:
            return f'CALL NEAR {ea}', raw_len, extra
        elif reg == 3:
            return f'CALL FAR {ea}', raw_len, extra
        elif reg == 4:
            return f'JMP NEAR {ea}', raw_len, extra
        elif reg == 5:
            return f'JMP FAR {ea}', raw_len, extra
        elif reg == 6:
            return f'PUSH {ea}', raw_len, extra
        else:
            return f'FF /{reg} {ea}', raw_len, extra

    # ── AAM (D4 0A) / AAD (D5 0A) / AAM imm8 / AAD imm8 ──
    if b == 0xD4:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            if imm == 0x0A:
                return 'AAM', raw_len, extra
            else:
                return f'AAM {imm:02X}h', raw_len, extra
        else:
            return 'AAM', raw_len, extra
    if b == 0xD5:
        if offset + 1 < len(data):
            imm = data[offset+1]
            raw_len = prefix_len + 2
            if imm == 0x0A:
                return 'AAD', raw_len, extra
            else:
                return f'AAD {imm:02X}h', raw_len, extra
        else:
            return 'AAD', raw_len, extra

    # ── SALC (aka SETC AL, D6) — undocumented ──
    if b == 0xD6: return 'SALC', raw_len, extra

    # ── FWAIT (9B) ──
    if b == 0x9B: return 'FWAIT', raw_len, extra

    # ── ESC (D8-DF) — FPU ──
    if 0xD8 <= b <= 0xDF:
        ea, consumed, modrm, reg, rm, mod = decode_modrm(data, offset+1, 2)
        raw_len = prefix_len + 1 + consumed
        return f'ESC {b-0xD8} {ea}', raw_len, extra

    # ── Unknown: emit DB ──
    return f'DB {b:02X}h', 1, extra


# ─── Disassembly driver ────────────────────────────────────────────────────────

def disasm_region(data, start_off, end_off, label, seg_base=0, dgroup_base=0):
    """Disassemble a region of bytes, return list of formatted lines."""
    lines = []
    lines.append(f'\n{"="*72}')
    lines.append(f'  {label}')
    lines.append(f'  File offset: 0x{start_off:05X} - 0x{end_off:05X}  ({end_off - start_off} bytes)')
    lines.append(f'{"="*72}')
    lines.append(f'{"Offset":<10} {"Raw":<12} {"Instruction":<45} {"Notes"}')
    lines.append(f'{"-"*72}')

    off = start_off
    while off < end_off:
        inst_start = off
        # Get raw bytes for display (up to 8 bytes max)
        raw_display_limit = min(8, end_off - off)
        raw_bytes = data[off:off+raw_display_limit]

        # Disassemble
        text, raw_len, extra = disasm_instruction(data, off, seg_base, dgroup_base)

        # Build raw bytes string
        raw_hex = ' '.join(f'{data[off+i]:02X}' for i in range(min(raw_len, 8)))
        if raw_len > 8:
            raw_hex += ' ...'

        # Format the line
        line = f'{off:05X}h    {raw_hex:<12} {text:<45}'
        if extra:
            line += f' {extra}'
        lines.append(line)

        off += max(raw_len, 1)

    return lines


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    exe_path = os.path.join(script_dir, '..', 'data', 'MTU.EXE')
    output_dir = os.path.join(script_dir, '..', 'output')

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(exe_path, 'rb') as f:
        exe = f.read()

    # DGROUP base (segment 6, file 0x19E00)
    dgroup_base = 0x19E00

    # Seg3 starts at file 0xA200
    seg3_start = 0xA200

    all_lines = []
    all_lines.append('MTU.EXE — Seg3 x86-16 Disassembly')
    all_lines.append(f'Executable size: {len(exe)} bytes')
    all_lines.append(f'Seg3 file offset: 0x{seg3_start:05X}')
    all_lines.append(f'DGROUP file offset: 0x{dgroup_base:05X}')
    all_lines.append('')

    # Region 1: Section 3 Entry Lookup — file 0x0C463 to 0x0C800
    # This is at Seg3+0x2263 (0x1C60 from seg3 base = 0xA200 + 0x2263 = 0xC463)
    region1_lines = disasm_region(
        exe, 0x0C463, 0x0C800,
        'Section 3 Entry Lookup (Seg3+0x2263)',
        seg_base=seg3_start, dgroup_base=dgroup_base
    )
    all_lines.extend(region1_lines)

    # Region 2: Another dictionary function — file 0x0D159 to 0x0D500
    # Seg3+0x2F59 (0xA200 + 0x2F59 = 0xD159)
    region2_lines = disasm_region(
        exe, 0x0D159, 0x0D500,
        'Dictionary Function (Seg3+0x2F59)',
        seg_base=seg3_start, dgroup_base=dgroup_base
    )
    all_lines.extend(region2_lines)

    # Region 3: Dictionary loader — file 0x0A6BD to 0x0AA00
    # Seg3+0x004BD (0xA200 + 0x04BD = 0xA6BD)
    region3_lines = disasm_region(
        exe, 0x0A6BD, 0x0AA00,
        'Dictionary Loader (Seg3+0x04BD)',
        seg_base=seg3_start, dgroup_base=dgroup_base
    )
    all_lines.extend(region3_lines)

    # Summary
    all_lines.append('')
    all_lines.append(f'{"="*72}')
    all_lines.append(f'  Summary')
    all_lines.append(f'{"="*72}')
    all_lines.append(f'  Region 1: 0x0C463-0x0C800 (Section 3 Entry Lookup)')
    all_lines.append(f'  Region 2: 0x0D159-0x0D500 (Dictionary Function)')
    all_lines.append(f'  Region 3: 0x0A6BD-0x0AA00 (Dictionary Loader)')
    all_lines.append(f'  DGROUP base (file): 0x{dgroup_base:05X}')
    all_lines.append(f'  Seg3 base (file): 0x{seg3_start:05X}')

    output_text = '\n'.join(all_lines)

    # Write to file
    output_path = os.path.join(output_dir, 'DISASM_SEG3.TXT')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_text)
        f.write('\n')

    print(output_text)
    print(f'\nDisassembly saved to: {output_path}')


if __name__ == '__main__':
    main()
