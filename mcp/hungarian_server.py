#!/usr/bin/env python3
"""
Franz Hungarian MCP Server
Eszközök: Magyar helyesírás, szótár, szövegstatisztika, ékezet javítás
"""

from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

server = Server("franz-hungarian")

# ── Egyszerű Magyar helyesírási szabályok (Hunspell nélkül) ───
# Gyakori hibák: ékezet nélküli változat → helyes alak
_COMMON_FIXES: dict[str, str] = {
    "igy": "így",
    "ugy": "úgy",
    "mar": "már",
    "meg": "még",
    "kesz": "kész",
    "tobbet": "többet",
    "tobb": "több",
    "kerek": "kérek",
    "kerlek": "kérlek",
    "megis": "mégis",
    "miert": "miért",
    "kozben": "közben",
    "kozel": "közel",
    "kozos": "közös",
    "egyutt": "együtt",
    "kulonben": "különben",
    "fugg": "függ",
    "unnep": "ünnep",
    "utolso": "utolsó",
    "elso": "első",
    "masodik": "második",
    "otodik": "ötödik",
    "csinalnom": "csinálnom",
    "csinalod": "csinálod",
    "csinalom": "csinálom",
    "csinal": "csinál",
    "mondanom": "mondanom",
    "latom": "látom",
    "latjuk": "látjuk",
    "erdekli": "érdekli",
    "erdekes": "érdekes",
    "akar": "akar",
    "akarom": "akarom",
    "szamomra": "számomra",
    "szamara": "számára",
    "szamitogep": "számítógép",
    "programozas": "programozás",
    "fejlesztes": "fejlesztés",
    "konyvtar": "könyvtár",
    "valtozok": "változók",
    "valtozo": "változó",
    "fuggveny": "függvény",
    "fuggvenyek": "függvények",
    "osztaly": "osztály",
    "osztalyok": "osztályok",
    "modszer": "módszer",
    "modszerek": "módszerek",
    "tipusos": "típusos",
    "tipushiba": "típushiba",
    "hasonlo": "hasonló",
    "kulonbozo": "különböző",
    "mukodesre": "működésre",
    "mukodik": "működik",
}

# Magyar szavak ékezet nélküli → ékezetes formák (gyakori)
_ACCENT_MAP: dict[str, list[str]] = {
    "a": ["á"],
    "e": ["é"],
    "i": ["í"],
    "o": ["ó", "ö", "ő"],
    "u": ["ú", "ü", "ű"],
}

# Magyar számok
_HU_NUMBERS = {
    0: "nulla", 1: "egy", 2: "kettő", 3: "három", 4: "négy",
    5: "öt", 6: "hat", 7: "hét", 8: "nyolc", 9: "kilenc",
    10: "tíz", 11: "tizenegy", 12: "tizenkettő", 13: "tizenhárom",
    14: "tizennégy", 15: "tizenöt", 16: "tizenhat", 17: "tizenhét",
    18: "tizennyolc", 19: "tizenkilenc", 20: "húsz",
    30: "harminc", 40: "negyven", 50: "ötven",
    60: "hatvan", 70: "hetven", 80: "nyolcvan", 90: "kilencven",
    100: "száz", 1000: "ezer", 1_000_000: "millió",
}


def _number_to_hungarian(n: int) -> str:
    """Szám → magyar szó."""
    if n in _HU_NUMBERS:
        return _HU_NUMBERS[n]
    if n < 0:
        return f"mínusz {_number_to_hungarian(-n)}"
    if n < 100:
        tens = (n // 10) * 10
        ones = n % 10
        return _HU_NUMBERS[tens] + _HU_NUMBERS[ones]
    if n < 1000:
        h = n // 100
        rest = n % 100
        prefix = ("" if h == 1 else _number_to_hungarian(h)) + "száz"
        return prefix + (_number_to_hungarian(rest) if rest else "")
    if n < 1_000_000:
        t = n // 1000
        rest = n % 1000
        prefix = ("" if t == 1 else _number_to_hungarian(t)) + "ezer"
        return prefix + (_number_to_hungarian(rest) if rest else "")
    return str(n)


_ACCENT_EXEMPT = {
    "egy", "magyar", "csak", "vagy", "van", "nem", "meg", "de", "az", "a",
    "is", "ha", "hogy", "mert", "ez", "azt", "azt", "ezt", "lesz", "volt",
    "igen", "nem", "cs", "sz", "gy", "ny", "ly", "by", "fly", "sky",
    "python", "golang", "javascript", "typescript", "docker", "kubernetes",
    "linux", "windows", "macos", "android", "system", "class", "import",
    "function", "return", "async", "await", "print", "string", "integer",
}


def _detect_missing_accents(text: str) -> list[str]:
    """Gyanús ékezet nélküli szavak detektálása."""
    suspicious = []
    words = re.findall(r"\b[a-zA-Z]+\b", text)
    hu_patterns = re.compile(r"(cs|sz|zs|gy|ny|ty|ly|dz|dzs)", re.I)
    for word in words:
        lower = word.lower()
        if lower in _ACCENT_EXEMPT:
            continue
        # Ha tartalmaz tipikus magyar mássalhangzó-párt de nincs ékezete
        if hu_patterns.search(lower) and not any(
            c in word for c in "áéíóöőúüű"
        ):
            suspicious.append(word)
    return list(set(suspicious))


def _check_hunspell(text: str) -> str:
    """Hunspell-lel ellenőrzi ha elérhető."""
    try:
        result = subprocess.run(
            ["hunspell", "-d", "hu_HU", "-l"],
            input=text,
            capture_output=True,
            text=True,
            timeout=10,
        )
        wrong = [w.strip() for w in result.stdout.splitlines() if w.strip()]
        if not wrong:
            return "✓ Nincs helyesírási hiba (Hunspell hu_HU)."
        return "Gyanús szavak:\n" + "\n".join(f"  • {w}" for w in wrong)
    except FileNotFoundError:
        return None  # type: ignore[return-value]
    except Exception as e:
        return f"[HUNSPELL HIBA] {e}"


def _spell_check(text: str) -> str:
    """Magyar helyesírás ellenőrzés."""
    # 1. Hunspell ha elérhető
    hunspell_result = _check_hunspell(text)
    if hunspell_result:
        return hunspell_result

    # 2. Fallback: ékezet detekció + ismert hibák
    lines = []
    suspicious = _detect_missing_accents(text)
    if suspicious:
        lines.append("Esetleg hiányzó ékezetek (ellenőrizd):")
        for w in suspicious:
            lines.append(f"  • {w}")

    # Ismert hibaminták
    text_lower = text.lower()
    for wrong, correct in _COMMON_FIXES.items():
        if wrong in text_lower:
            lines.append(f"  Lehet: '{wrong}' → '{correct}'?")

    if not lines:
        return "✓ Nem találtam nyilvánvaló hibát. (Hunspell nincs telepítve — `brew install hunspell` ajánlott)"
    return "\n".join(lines) + "\n\n[Pontosabb ellenőrzéshez: `brew install hunspell` + hu_HU szótár]"


def _word_stats(text: str) -> str:
    """Szövegstatisztika magyarul."""
    words = re.findall(r"\b\w+\b", text, re.UNICODE)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    chars = len(text)
    chars_no_space = len(text.replace(" ", ""))

    # Leggyakoribb szavak (stopszavak nélkül)
    stopwords = {"a", "az", "és", "is", "de", "hogy", "nem", "van", "egy", "ez", "az", "vagy"}
    freq: dict[str, int] = {}
    for w in words:
        wl = w.lower()
        if wl not in stopwords and len(wl) > 2:
            freq[wl] = freq.get(wl, 0) + 1
    top = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]

    lines = [
        f"Szavak: {len(words)}",
        f"Mondatok: {len(sentences)}",
        f"Karakterek: {chars} (szóközök nélkül: {chars_no_space})",
        f"Átlagos szóhossz: {sum(len(w) for w in words)/max(len(words),1):.1f} karakter",
        f"Átlagos mondathossz: {len(words)/max(len(sentences),1):.1f} szó",
    ]
    if top:
        lines.append("Leggyakoribb szavak: " + ", ".join(f"{w}({n})" for w, n in top))
    return "\n".join(lines)


def _fix_accents(text: str) -> str:
    """
    Ékezet nélküli szöveg 'javítása' — csak nyilvánvaló eseteket.
    Pl. 'a' → 'á' ha az összefüggés alapján egyértelmű.
    Ez egy egyszerű, szótár alapú csere.
    """
    result = text
    for wrong, correct in _COMMON_FIXES.items():
        # Case-insensitive csere, eredeti case megőrzésével
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)
        result = pattern.sub(correct, result)

    if result == text:
        return f"(Nem találtam egyértelmű javítást)\n\nEredeti: {text}"
    return f"Javított:\n{result}\n\nEredeti:\n{text}"


def _number_to_words(text: str) -> str:
    """Számok átírása magyar szavakba."""
    def replace_num(m: re.Match) -> str:
        try:
            n = int(m.group())
            if 0 <= n <= 999_999_999:
                return _number_to_hungarian(n)
        except ValueError:
            pass
        return m.group()

    result = re.sub(r"\b\d+\b", replace_num, text)
    return result


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="spell_check",
            description="Magyar helyesírás ellenőrzés. Hunspell ha elérhető, egyébként ékezet-alapú elemzés.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Az ellenőrzendő magyar szöveg"},
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="word_stats",
            description="Szövegstatisztika: szószám, mondatszám, karakterszám, leggyakoribb szavak.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Az elemzendő szöveg"},
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="fix_accents",
            description="Ékezet nélküli magyar szöveg javítása ismert szótár alapján.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Az ékezet nélküli magyar szöveg"},
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="number_to_words",
            description="Számok átírása magyar szavakba. Pl. '42' → 'negyvenkettő'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Szöveg számokkal, pl. '42 alma'"},
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="detect_language",
            description="Megállapítja, hogy a szöveg valószínűleg magyar-e (ékezetek + tipikus szavak alapján).",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Az elemzendő szöveg"},
                },
                "required": ["text"],
            },
        ),
    ]


def _detect_language(text: str) -> str:
    """Egyszerű Magyar nyelvdetektálás."""
    hu_chars = sum(1 for c in text if c in "áéíóöőúüűÁÉÍÓÖŐÚÜŰ")
    total_chars = len([c for c in text if c.isalpha()])

    hu_words = {"és", "az", "egy", "van", "nem", "hogy", "de", "is", "meg",
                "volt", "lesz", "már", "még", "csak", "vagy", "aki", "ami",
                "mert", "ha", "én", "te", "ő", "mi", "ti", "ők", "igen"}
    words_lower = set(re.findall(r"\b\w+\b", text.lower()))
    hu_word_hits = len(hu_words & words_lower)

    hu_ratio = hu_chars / max(total_chars, 1)
    # Magyar mássalhangzó-párok jelenléte (cs, sz, zs, gy, ny, ty, ly)
    hu_digraphs = len(re.findall(r"cs|sz|zs|gy|ny|ty|ly|dz", text.lower()))
    digraph_score = min(hu_digraphs / 3, 1.0) * 0.2
    score = hu_ratio * 0.5 + min(hu_word_hits / 3, 1.0) * 0.3 + digraph_score

    if score > 0.3:
        verdict = "Valószínűleg MAGYAR"
    elif score > 0.15:
        verdict = "Lehet magyar (bizonytalan)"
    else:
        verdict = "Valószínűleg NEM magyar"

    return (
        f"{verdict}\n"
        f"  Ékezetes arány: {hu_ratio:.1%}\n"
        f"  Magyar kulcsszavak: {hu_word_hits}\n"
        f"  Megbízhatóság: {score:.1%}"
    )


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "spell_check":
        result = _spell_check(arguments["text"])
    elif name == "word_stats":
        result = _word_stats(arguments["text"])
    elif name == "fix_accents":
        result = _fix_accents(arguments["text"])
    elif name == "number_to_words":
        result = _number_to_words(arguments["text"])
    elif name == "detect_language":
        result = _detect_language(arguments["text"])
    else:
        result = f"[HIBA] Ismeretlen eszköz: {name}"

    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="franz-hungarian",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
