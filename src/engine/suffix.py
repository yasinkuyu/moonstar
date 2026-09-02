# -*- coding: utf-8 -*-
"""
engine/suffix.py — Suffix Table Management & Morphological Derivation Engine
"""

import json
import os
import sys
from typing import List, Optional

# Ensure src root is accessible for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import ALL_VOWELS, BACK_VOWELS
from engine.phonetics import (
    attach_suffix_phonetically,
    get_last_vowel,
    is_back_vowel,
    soften_final_consonant,
)

_CACHED_SUFFIX_TABLE: List[str] = []


def get_suffix_table() -> List[str]:
    """Returns the cached 3,218 Section 3 suffix table, loading lazily."""
    global _CACHED_SUFFIX_TABLE
    if _CACHED_SUFFIX_TABLE:
        return _CACHED_SUFFIX_TABLE

    cur_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(cur_dir, "..", "..", "data", "suffixes.json"),
        os.path.join(cur_dir, "..", "data", "suffixes.json"),
        "data/suffixes.json",
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                _CACHED_SUFFIX_TABLE = json.load(f)
                return _CACHED_SUFFIX_TABLE
    return _CACHED_SUFFIX_TABLE


class SuffixEngine:
    """Handles morphological suffix application using Section 3 binary rules."""

    def __init__(self, suffix_table: Optional[List[str]] = None):
        self.suffix_table = suffix_table or get_suffix_table()

    def get_suffix_text(self, suf_id: int) -> Optional[str]:
        """Resolves 16-bit Section 3 suffix ID to string."""
        if 0 <= suf_id < len(self.suffix_table):
            val = self.suffix_table[suf_id]
            return val if val else None
        return None

    def apply_suffix(self, root: str, suf_id: int) -> str:
        """Applies a 16-bit Section 3 suffix instruction to a root word."""
        if not root:
            return root

        vowels = [c for c in root if c in ALL_VOWELS]
        last_v = vowels[-1] if vowels else "a"
        is_back = last_v in BACK_VOWELS

        if suf_id in [0x07EF, 0x07DC, 0xDC07, 0xEF07]:  # -sız / -siz / -suz / -süz
            return root + ("sız" if last_v in "aıâ" else ("siz" if last_v in "eiî" else ("suz" if last_v in "ouû" else "süz")))
        elif suf_id in [0x04BB, 0xBB04]:  # -lıksız / -liksiz / -lüksüz
            return root + ("lıksız" if last_v in "aıâ" else ("liksiz" if last_v in "eiî" else ("luksus" if last_v in "ouû" else "lüksüz")))
        elif suf_id in [0x048A, 0x0498, 0x04A6, 0x04B4, 0x0488, 0x8804, 0x8488]:  # -lık / -lik / -luk / -lük / -lığı / -liği
            if suf_id in [0x0488, 0x8804, 0x8488]:
                return root + ("lığ" if last_v in "aıâ" else ("liğ" if last_v in "eiî" else ("luğ" if last_v in "ouû" else "lüğ")))
            return root + ("lık" if last_v in "aıâ" else ("lik" if last_v in "eiî" else ("luk" if last_v in "ouû" else "lük")))
        elif suf_id in [0x04A2, 0x0486, 0x04B0, 0x0494, 0x9404, 0x8604, 0xB004]:  # -lı / -li / -lu / -lü
            return root + ("lı" if last_v in "aıâ" else ("li" if last_v in "eiî" else ("lu" if last_v in "ouû" else "lü")))
        elif suf_id in [0x07DF, 0x0805]:  # -sızlık / -sizlik / -suzluk / -süzlük
            return root + ("sızlık" if last_v in "aıâ" else ("sizlik" if last_v in "eiî" else ("suzluk" if last_v in "ouû" else "süzlük")))
        elif suf_id == 0x035C:  # -ın / -in (çek -> çekin)
            return root + ("ın" if last_v in "aı" else ("in" if last_v in "ei" else ("un" if last_v in "ou" else "ün")))
        elif suf_id == 0x02AA:  # -ına / -ine (baş -> başına)
            return root + ("ına" if last_v in "aıâ" else ("ine" if last_v in "eiî" else ("una" if last_v in "ouû" else "üne")))
        elif suf_id in [0x0000, 0x01FF, 0xFF01]:  # -a / -e (yönelme/dative: can -> cana, tarih -> tarihe)
            if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")):
                return root + ("ya" if is_back else "ye")
            return root + ("a" if is_back else "e")
        elif suf_id in [0x09FF, 0xFF09]:  # -ıp / -ip / -up / -üp (göç -> göçüp)
            r = root[:-1] if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")) else root
            return r + ("up" if last_v in "ouû" else ("üp" if last_v in "öü" else ("ıp" if last_v in "aıâ" else "ip")))
        elif suf_id in [0x0292, 0x9202]:  # -ıl / -il / -ul / -ül (edilgen: aç -> açıl)
            return root + ("ul" if last_v in "ouû" else ("ül" if last_v in "öü" else ("ıl" if last_v in "aıâ" else "il")))
        elif suf_id in [0x0980, 0x0A32, 0x320A, 0x02F9, 0xF902, 0x03AC, 0xAC03]:  # -uş / -üş / -ış / -iş (uy -> uyuş, göç -> göçüş, aç -> açış, gir -> giriş)
            r = root[:-1] if root.endswith(("a", "ı", "o", "u", "e", "i", "ö", "ü")) else root
            return r + ("uş" if last_v in "ouû" else ("üş" if last_v in "öü" else ("ış" if last_v in "aıâ" else "iş")))
        elif suf_id in [0x0B7E, 0x7E0B]:  # -yış / -yiş (başla -> başlayış)
            return root + ("yış" if is_back else "yiş")
        elif suf_id in [0x0831, 0x3108]:  # -ta / -te / -da / -de (baş -> başta)
            return root + ("ta" if is_back else "te")
        elif suf_id == 0x0507:  # -ma / -me (çekinme / yeme)
            return root + ("ma" if is_back else "me")
        elif suf_id in [0x0C36, 0x0C33, 0x330C]:  # -z (çekinmez / yemez / çıkmaz / açmaz)
            return root + "z"
        elif suf_id in [0x028F, 0x8F02]:  # -ı / -i (iyelik)
            r = soften_final_consonant(root)
            return r + ("ı" if last_v in "aı" else ("i" if last_v in "ei" else ("u" if last_v in "ou" else "ü")))
        elif suf_id in [0x0834, 0x3408]:  # -den / -dan / -ten / -tan
            return root + ("tan" if last_v in "aı" else "ten")
        elif suf_id in [0x0127, 0x2701]:  # -de / -da
            return root + ("da" if last_v in "aı" else "de")
        elif suf_id in [0x0245, 0x4502]:  # -en / -an
            return root + ("an" if is_back else "en")
        elif suf_id in [0x04C6, 0xC604, 0x0506, 0x0605, 0x04CA, 0xCA04, 0x04C5, 0xC504]:  # -me / -ma
            return root + ("ma" if is_back else "me")
        elif suf_id in [0x0AC1, 0xC10A]:  # -yen / -yan
            return root + ("yan" if is_back else "yen")
        elif suf_id in [0x0797, 0x9707, 0x07B4, 0xB407]:  # -sal / -sel
            return root + ("sal" if is_back else "sel")
        elif suf_id in [0x07DB, 0xDB07]:  # -sıyla / -siyle (fazla -> fazlasıyla)
            return root + ("sıyla" if is_back else "siyle")
        elif suf_id in [0x07CD, 0xCD07]:  # -sı / -si
            return root + ("sı" if last_v in "aı" else ("si" if last_v in "ei" else ("su" if last_v in "ou" else "sü")))
        elif suf_id in [0x0290, 0x9002, 0x0090, 0x9000]:  # -ı / -i
            res = soften_final_consonant(root)
            return res + ("ı" if last_v in "aı" else "i")
        elif suf_id in [0x0447, 0x0407, 0x8447, 0x4784, 0x8407, 0x0784, 0x00C9, 0xC900, 0x0446, 0x4604]:  # -la / -le
            return root + ("la" if is_back else "le")
        elif suf_id in [0x050B, 0x0B05]:  # -mak / -mek
            return root + ("mak" if is_back else "mek")
        elif suf_id in [0x04FE, 0xFE04, 0x053F, 0x3F05]:  # -maz / -mez
            return root + ("maz" if is_back else "mez")
        elif suf_id in [0x0097, 0x00A9, 0x00BB, 0x00CD, 0x00E3, 0x00F5, 0x0107, 0x0119]:  # -cık / -cik / -cuk / -cük / -çık / -çik / -çuk / -çük
            c = "ç" if root.endswith(("p", "ç", "t", "k", "s", "ş", "h", "f")) else "c"
            v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
            return root + c + v + "k"
        elif suf_id in [0x008E, 0x0091]:  # -cağız / -ceğiz
            return root + ("cağız" if is_back else "ceğiz")
        elif suf_id == 0x0046:  # -daş / -deş / -taş / -teş
            d = "t" if root.endswith(("p", "ç", "t", "k", "s", "ş", "h", "f")) else "d"
            return root + d + ("aş" if is_back else "eş")
        elif suf_id in [0x040D, 0x040E, 0x044D, 0x044E]:  # -ler / -lar
            return root + ("lar" if is_back else "ler")
        elif suf_id in [0x0543, 0x0544, 0x0545, 0x0598, 0x0599, 0x059A]:  # -mış / -miş / -muş / -müş
            v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
            return root + "m" + v + "ş"
        elif suf_id in [0x0408, 0x0448]:  # -lan / -len
            return root + ("lan" if is_back else "len")
        elif suf_id in [0x043F, 0x047F]:  # -laş / -leş
            return root + ("laş" if is_back else "leş")
        elif suf_id in [0x094D, 0x094E]:  # -ca / -ce
            c = "ç" if root.endswith(("p", "ç", "t", "k", "s", "ş", "h", "f")) else "c"
            return root + c + ("a" if is_back else "e")
        elif suf_id == 0x03F5:  # -ken
            return root + "ken"
        elif suf_id == 0x0345:  # -ci / -cı / -cu / -cü
            c = "ç" if root.endswith(("p", "ç", "t", "k", "s", "ş", "h", "f")) else "c"
            v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
            return root + c + v
        elif suf_id == 0x0802:  # -suz / -süz / -sız / -siz
            return root + ("suz" if last_v in "ouû" else ("süz" if last_v in "öü" else ("sız" if last_v in "aıâ" else "siz")))
        elif suf_id in [0x0342, 0x0343, 0x4303, 0x0915, 0x0916, 0x01FF]:  # -ı / -i / -u / -ü (tamlanan / iyelik)
            res = root
            if res.endswith("k") and res not in ["ok", "kök", "ek", "ak"]:
                res = res[:-1] + "ğ"
            elif res.endswith("p"):
                res = res[:-1] + "b"
            v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
            if res.endswith(tuple(ALL_VOWELS)):
                return res + "s" + v
            return res + v
        elif suf_id in [0x0B8B, 0x8B0B]:  # " biçmek"
            return root + " biçmek"
        elif suf_id == 0x0C3B:  # -ıcı / -ici / -ucu / -ücü
            v = "u" if last_v in "ouû" else ("ü" if last_v in "öü" else ("ı" if last_v in "aıâ" else "i"))
            return root + v + "c" + v

        # Dynamic fallback to 3,218 Section 3 suffix table
        suf_text = self.get_suffix_text(suf_id)
        if suf_text:
            return attach_suffix_phonetically(root, suf_text)

        # Byte-swapped check
        swapped = (((suf_id & 0xFF) << 8) | ((suf_id >> 8) & 0xFF)) & 0x7FFF
        suf_text = self.get_suffix_text(swapped)
        if suf_text:
            return attach_suffix_phonetically(root, suf_text)

        return root
