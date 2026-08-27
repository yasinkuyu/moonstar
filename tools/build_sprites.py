#!/usr/bin/env python3
"""
Pure Python Sprite Sheet Generator
Reads PNG files (palette, RGBA, RGB) and stitches them into sprite sheets.
No external dependencies required (uses only stdlib zlib, struct).
"""
import os
import struct
import zlib

def read_png(path):
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', f"Not a PNG: {path}"
    
    pos = 8
    width = height = bit_depth = color_type = None
    palette = []
    transparency = None
    idat = []
    
    while pos < len(data):
        length, chunk_type = struct.unpack('>I4s', data[pos:pos+8])
        pos += 8
        chunk_data = data[pos:pos+length]
        pos += length + 4 # skip crc
        
        if chunk_type == b'IHDR':
            width, height, bit_depth, color_type, comp, filt, inter = struct.unpack('>IIBBBBB', chunk_data)
            assert bit_depth == 8, f"Only 8-bit depth supported: {path} (got {bit_depth})"
            assert inter == 0, f"Interlacing not supported: {path}"
        elif chunk_type == b'PLTE':
            palette = [chunk_data[i:i+3] for i in range(0, len(chunk_data), 3)]
        elif chunk_type == b'tRNS':
            transparency = chunk_data
        elif chunk_type == b'IDAT':
            idat.append(chunk_data)
        elif chunk_type == b'IEND':
            break
            
    raw = zlib.decompress(b''.join(idat))
    
    # Unfilter lines to RGBA (width x height x 4 bytes)
    pixels = bytearray(width * height * 4)
    
    bytes_per_pixel = {
        0: 1, # Grayscale
        2: 3, # RGB
        3: 1, # Palette
        4: 2, # Gray + Alpha
        6: 4  # RGBA
    }[color_type]
    
    stride = width * bytes_per_pixel
    prev_row = bytearray(stride)
    src_pos = 0
    
    unfiltered_rows = []
    for y in range(height):
        filter_type = raw[src_pos]
        src_pos += 1
        curr_row = bytearray(raw[src_pos:src_pos+stride])
        src_pos += stride
        
        bpp = bytes_per_pixel
        for x in range(stride):
            a = curr_row[x - bpp] if x >= bpp else 0
            b = prev_row[x]
            c = prev_row[x - bpp] if x >= bpp else 0
            
            if filter_type == 0:   # None
                pass
            elif filter_type == 1: # Sub
                curr_row[x] = (curr_row[x] + a) & 0xFF
            elif filter_type == 2: # Up
                curr_row[x] = (curr_row[x] + b) & 0xFF
            elif filter_type == 3: # Average
                curr_row[x] = (curr_row[x] + ((a + b) >> 1)) & 0xFF
            elif filter_type == 4: # Paeth
                p = a + b - c
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                curr_row[x] = (curr_row[x] + pr) & 0xFF
            else:
                raise ValueError(f"Unknown filter type {filter_type}")
                
        prev_row = curr_row
        unfiltered_rows.append(curr_row)
        
    # Convert all to standard 32-bit RGBA
    for y in range(height):
        row = unfiltered_rows[y]
        for x in range(width):
            out_idx = (y * width + x) * 4
            if color_type == 6: # RGBA
                in_idx = x * 4
                pixels[out_idx:out_idx+4] = row[in_idx:in_idx+4]
            elif color_type == 2: # RGB
                in_idx = x * 3
                pixels[out_idx:out_idx+3] = row[in_idx:in_idx+3]
                pixels[out_idx+3] = 255
            elif color_type == 3: # Palette
                pal_idx = row[x]
                if pal_idx < len(palette):
                    pixels[out_idx:out_idx+3] = palette[pal_idx]
                    alpha = transparency[pal_idx] if transparency and pal_idx < len(transparency) else 255
                    pixels[out_idx+3] = alpha
                else:
                    pixels[out_idx:out_idx+4] = b'\x00\x00\x00\x00'
            elif color_type == 0: # Grayscale
                v = row[x]
                pixels[out_idx:out_idx+3] = bytes([v, v, v])
                pixels[out_idx+3] = 255
                
    return width, height, pixels

def write_png(path, width, height, rgba_pixels):
    # Pack with filter type 0 (None)
    raw = bytearray()
    row_bytes = width * 4
    for y in range(height):
        raw.append(0) # Filter byte: None
        start = y * row_bytes
        raw.extend(rgba_pixels[start:start+row_bytes])
        
    compressed = zlib.compress(bytes(raw), level=9)
    
    def make_chunk(ctype, cdata):
        crc = zlib.crc32(ctype + cdata) & 0xFFFFFFFF
        return struct.pack('>I4s', len(cdata), ctype) + cdata + struct.pack('>I', crc)
        
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    out = bytearray(b'\x89PNG\r\n\x1a\n')
    out.extend(make_chunk(b'IHDR', ihdr_data))
    out.extend(make_chunk(b'IDAT', compressed))
    out.extend(make_chunk(b'IEND', b''))
    
    with open(path, 'wb') as f:
        f.write(out)
    print(f"  ✅ Written: {path} ({width}x{height}, {len(out)} bytes)")

class SpriteCanvas:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 4)
        
    def blit(self, src_pixels, src_w, src_h, dest_x, dest_y):
        for y in range(src_h):
            dy = dest_y + y
            if dy < 0 or dy >= self.height: continue
            for x in range(src_w):
                dx = dest_x + x
                if dx < 0 or dx >= self.width: continue
                s_idx = (y * src_w + x) * 4
                d_idx = (dy * self.width + dx) * 4
                self.pixels[d_idx:d_idx+4] = src_pixels[s_idx:s_idx+4]
                
    def save(self, path):
        write_png(path, self.width, self.height, self.pixels)

def build_all_sprites():
    print("🎨 Building Sprite Sheets...")
    
    # 1. Keys Sprite Sheet (30 keys, normal on row 0, pressed on row 1)
    keys_w = 30 * 25 # 750px
    keys_h = 2 * 25  # 50px
    keys_canvas = SpriteCanvas(keys_w, keys_h)
    
    for i in range(30):
        idx_str = f"{i:02d}"
        n_path = f"assets/keys/n_{idx_str}.png"
        p_path = f"assets/keys/p_{idx_str}.png"
        
        if os.path.exists(n_path):
            w, h, px = read_png(n_path)
            keys_canvas.blit(px, w, h, i * 25, 0)
        if os.path.exists(p_path):
            w, h, px = read_png(p_path)
            keys_canvas.blit(px, w, h, i * 25, 25)
            
    keys_canvas.save("assets/keys_sprite.png")
    
    # 2. Gallows Sprite Sheet (10 stages, 52x76 each)
    gal_w = 10 * 52 # 520px
    gal_h = 76
    gal_canvas = SpriteCanvas(gal_w, gal_h)
    
    for i in range(10):
        hm_path = f"assets/hm_{i}.png"
        if os.path.exists(hm_path):
            w, h, px = read_png(hm_path)
            gal_canvas.blit(px, w, h, i * 52, 0)
            
    gal_canvas.save("assets/gallows_sprite.png")
    
    # 3. Main Buttons Sprite Sheet
    # Toolbar buttons (104x50) and Dialog buttons (63x39)
    btn_w = 624
    btn_h = 50 + 50 + 39 + 39 # 178px
    btn_canvas = SpriteCanvas(btn_w, btn_h)
    
    toolbar_buttons = [
        ("btn_denetim", "btn_denetim_p"),
        ("btn_tr_en", "btn_tr_en_p"),
        ("btn_esanlam", "btn_esanlam_p"),
        ("btn_klavye", "btn_klavye_p"),
        ("btn_en_tr", "btn_en_tr_p"),
        ("btn_adam_asma", "btn_adam_asma_p"),
    ]
    
    for col, (norm, press) in enumerate(toolbar_buttons):
        np = f"assets/{norm}.png"
        pp = f"assets/{press}.png"
        if os.path.exists(np):
            w, h, px = read_png(np)
            btn_canvas.blit(px, w, h, col * 104, 0)
        if os.path.exists(pp):
            w, h, px = read_png(pp)
            btn_canvas.blit(px, w, h, col * 104, 50)
            
    dialog_buttons_row1 = [
        "btn_tamam",
        "btn_iptal",
        "btn_edit",
        "btn_sozluk",
        "btn_basla",
        "btn_degistir_d",
    ]
    
    dialog_buttons_row2 = [
        "btn_tamam_p",
        "btn_iptal_p",
        "btn_edit_p",
    ]
    
    y_r2 = 100
    for col, name in enumerate(dialog_buttons_row1):
        p = f"assets/{name}.png"
        if os.path.exists(p):
            w, h, px = read_png(p)
            btn_canvas.blit(px, w, h, col * 63, y_r2)
            
    y_r3 = 100 + 39
    for col, name in enumerate(dialog_buttons_row2):
        p = f"assets/{name}.png"
        if os.path.exists(p):
            w, h, px = read_png(p)
            btn_canvas.blit(px, w, h, col * 63, y_r3)
            
    btn_canvas.save("assets/buttons_sprite.png")
    print("✨ Sprite Generation Complete!")

if __name__ == '__main__':
    build_all_sprites()
