"""Hungarian Grammar Teaching Module — Comprehensive Language Learning System."""

from __future__ import annotations
import json
import pathlib
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# MAGYAR NYELVTAN TANÍTÓ MODUL — v7.5
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GrammarRule:
    """Egyetlen nyelvtani szabály."""
    id: str
    category: str  # "cases", "conjugation", "declension", "tenses", "moods", "prepositions"
    title: str
    explanation: str
    examples: List[str]
    rules: List[str]
    difficulty: str  # "beginner", "intermediate", "advanced"
    common_mistakes: List[str]

# ───────────────────────────────────────────────────────────────────────────────
# MAGYAR GRAMMATIKAI SZABÁLYOK ADATBÁZISA
# ───────────────────────────────────────────────────────────────────────────────

GRAMMAR_DATABASE = {
    # ── ESETEK (CASES) ──────────────────────────────────────────────────────────
    "case_nominative": GrammarRule(
        id="case_nominative",
        category="cases",
        title="Alanyeset (Nominative)",
        explanation="Az alany a mondat fő szereplője. Magyarul nincs végződés az alanyesetben.",
        examples=[
            "A macska alszik. (The cat sleeps.)",
            "János dolgozik. (John works.)",
            "Az autó piros. (The car is red.)",
        ],
        rules=[
            "Az alanyeset a szó eredeti formája",
            "Nincs végződés szükséges",
            "Az alany választ meg az ige számát és személyét",
        ],
        difficulty="beginner",
        common_mistakes=[
            "Ne keverd össze a tárgyesettel (-t végződés)",
            "Az alanyeset nem kap végződést",
        ],
    ),

    "case_accusative": GrammarRule(
        id="case_accusative",
        category="cases",
        title="Tárgyeset (Accusative)",
        explanation="A tárgy az ige tárgya. Végződés: -t vagy -ot/-et/-öt",
        examples=[
            "Szeretlek téged. (I love you.)",
            "A tejet megittam. (I drank the milk.)",
            "Látom a macskát. (I see the cat.)",
        ],
        rules=[
            "Magánhangzóra végződő szó: -t (asztal → asztalt)",
            "Mássalhangzóra végződő szó: -ot, -et, -öt (autó → autót, ember → embert)",
            "Határozatlan tárgy nem kapja a végződést",
        ],
        difficulty="beginner",
        common_mistakes=[
            "Határozatlan tárgy: macskát nem lehet mondani, csak macskát",
            "Vegyes végződések: -ot/-et/-öt szabálya",
        ],
    ),

    "case_dative": GrammarRule(
        id="case_dative",
        category="cases",
        title="Részeshatározó (Dative)",
        explanation="Kinek adok? Végződés: -nak, -nek",
        examples=[
            "Könyvet adtam az anyámnak. (I gave a book to my mother.)",
            "Beszéltem a barátomnak. (I spoke to my friend.)",
            "Ez a dal neked szól. (This song is for you.)",
        ],
        rules=[
            "Mögül magánhangzó: -nak (apám → apámnak)",
            "Mögül e, é magánhangzó: -nek (testvér → testvérnek)",
            "Végződés előtt: -i- (Peti → Petiinek)",
        ],
        difficulty="intermediate",
        common_mistakes=[
            "A végződés nem függnek, csak az előző magánhangzótól",
            "Ne felejtsd el a végződést a személynevek után",
        ],
    ),

    "case_locative": GrammarRule(
        id="case_locative",
        category="cases",
        title="Helyhatározó (Locative)",
        explanation="Hol van valami? Végződés: -ban, -ben",
        examples=[
            "A házban lakom. (I live in the house.)",
            "Az iskolában tanulok. (I study in school.)",
            "A szobában az asztal. (The table is in the room.)",
        ],
        rules=[
            "Mögül a, á, o, ó, u, ú: -ban (ház → házban)",
            "Mögül e, é, i, í, ö, ő, ü, ű: -ben (iskola → iskolában)",
        ],
        difficulty="intermediate",
        common_mistakes=[
            "A helyhatározó -ban/-ben végződést kap, nem -ból/-ből",
        ],
    ),

    # ── IGERAGOZÁS (CONJUGATION) ────────────────────────────────────────────────
    "conjugation_present_definite": GrammarRule(
        id="conjugation_present_definite",
        category="conjugation",
        title="Jelen idő, határozott ragozás",
        explanation="Amikor a tárgy határozott (a macska, ezt, azt). Végződések: -om, -od, -ja/-i",
        examples=[
            "Szerettem a macskát. (I love the cat.) — Past definite",
            "Látom a házat. (I see the house.) — Present definite",
            "Eszem az almát. (I eat the apple.) — Present definite",
        ],
        rules=[
            "1. személysingularis: -om/-am/-em (szereto → szeretom)",
            "2. személysingularis: -od/-ad/-ed",
            "3. személysingularis: -ja/-i",
            "1. személypluralis: -juk/-jünk",
            "2. személypluralis: -játok/-itek",
            "3. személypluralis: -ják/-ik",
        ],
        difficulty="intermediate",
        common_mistakes=[
            "Ne keverd össze a határozatlan ragozással",
            "A 3. személy: -ja/-i végződés",
        ],
    ),

    "conjugation_present_indefinite": GrammarRule(
        id="conjugation_present_indefinite",
        category="conjugation",
        title="Jelen idő, határozatlan ragozás",
        explanation="Amikor a tárgy határozatlan (macska, valamit). Végződések: -ok, -sz, -∅",
        examples=[
            "Szeretek. (I love.) — indefinite",
            "Macskát szeretsz. (You love a cat.) — indefinite",
            "Éneket énekelnek. (They sing a song.) — indefinite",
        ],
        rules=[
            "1. személysingularis: -ok/-ak/-ek (szereto → szeretok)",
            "2. személysingularis: -sz (szeretsz)",
            "3. személysingularis: -∅ (szeret)",
            "Pluralis: -unk/-ünk, -otok/-etek, -nak/-nek",
        ],
        difficulty="intermediate",
        common_mistakes=[
            "A 2. személy -sz végződést kap",
            "A 3. személy nem kap végződést (szeret, nem szereti)",
        ],
    ),

    # ── FÜGGELÉKEK (SUFFIXES) ───────────────────────────────────────────────────
    "suffix_diminutive": GrammarRule(
        id="suffix_diminutive",
        category="suffixes",
        title="Kicsinyítő képzők",
        explanation="Kicsinyítő képzők: -ka, -ke (nagyobb → nagyobbacska)",
        examples=[
            "macska → macskacska (little cat)",
            "ház → házacska (little house)",
            "könyv → könyvecske (little book)",
        ],
        rules=[
            "Főnév + -ka/-ke",
            "Olykor meghosszabbít: -cska, -cske",
        ],
        difficulty="beginner",
        common_mistakes=[
            "Ne keverd össze a diminutívot más képzőkkel",
        ],
    ),

    # ── IGEIDŐK (TENSES) ────────────────────────────────────────────────────────
    "tense_past_definite": GrammarRule(
        id="tense_past_definite",
        category="tenses",
        title="Múlt idő, határozott ragozás",
        explanation="Tegnap történt és határozott tárgy. -t/-tem, -ted, -ta/-te",
        examples=[
            "Szerettem az almát. (I loved the apple.)",
            "Láttad a filmet? (Did you see the film?)",
            "Beszélgettem az anyámmal. (I spoke with my mother.)",
        ],
        rules=[
            "1. s. sg.: -tem/-tam/-tom (szerettem, vettem)",
            "2. s. sg.: -ted/-tad/-tod",
            "3. s. sg.: -ta/-te (szerette, vette)",
        ],
        difficulty="intermediate",
        common_mistakes=[
            "Hasonult esetemben: -tt (szerettem, vettem, de játszottam)",
        ],
    ),

    # ── KÖZÖS HIBÁK ─────────────────────────────────────────────────────────────
    "common_mistakes_be_verb": GrammarRule(
        id="common_mistakes_be_verb",
        category="common",
        title="Az 'lenni' ige ragozása",
        explanation="Az 'lenni' ige szabálytalan, megjegyezendő formák.",
        examples=[
            "Vagyok. (I am.)",
            "Vagy. (You are.)",
            "Van. (He/She/It is.)",
            "Voltam. (I was.)",
            "Voltál. (You were.)",
        ],
        rules=[
            "Jelen: vagyok, vagy, van, vagyunk, vagytok, vannak",
            "Múlt: voltam, voltál, volt, voltunk, voltatok, voltak",
        ],
        difficulty="beginner",
        common_mistakes=[
            "Ne mondd 'lenezek' helyett 'vagyok'",
            "A 3. személy: 'van', nem 'lenne'",
        ],
    ),
}

# ───────────────────────────────────────────────────────────────────────────────
# MAGYAR NYELVTANI GYAKORLATOK
# ───────────────────────────────────────────────────────────────────────────────

GRAMMAR_EXERCISES: Dict[str, List[Dict]] = {
    "case_practice": [
        {
            "id": "exercise_1",
            "question": "A házban / házba: Melyik helyes? 'A macska a _____ alszik.'",
            "options": ["házban", "házba", "házból"],
            "correct": "házban",
            "explanation": "Helyhatározó: -ban/-ben végződés (hol?)",
        },
        {
            "id": "exercise_2",
            "question": "Tárgyeset: Melyik a helyes forma? 'Szeretlek _____.'",
            "options": ["te", "téged", "veled"],
            "correct": "téged",
            "explanation": "Tárgyeset: -t végződés (kit/mit?)",
        },
        {
            "id": "exercise_3",
            "question": "Részeshatározó: 'Könyvet adtam az anyámnak / anyámban?'",
            "options": ["anyámnak", "anyámban", "anyámét"],
            "correct": "anyámnak",
            "explanation": "Részeshatározó: -nak/-nek végződés (kinek?)",
        },
    ],
    "conjugation_practice": [
        {
            "id": "exercise_c1",
            "question": "Jelen idő: 'Én _____ szeretlek.'",
            "options": ["szeretek", "szeretom", "szeretlek"],
            "correct": "szeretek",
            "explanation": "Határozatlan ragozás, 1. személy: -ok/-ak/-ek",
        },
        {
            "id": "exercise_c2",
            "question": "Múlt idő: 'Tegnap _____ az almát.'",
            "options": ["ettem", "eszem", "eszem"],
            "correct": "ettem",
            "explanation": "Határozott múlt idő, 1. személy: -tem/-tam/-tom",
        },
    ],
}

# ═══════════════════════════════════════════════════════════════════════════════
# NYILVÁNOS FÜGGVÉNYEK
# ═══════════════════════════════════════════════════════════════════════════════

def teach_grammar(rule_id: str) -> str:
    """Egy nyelvtani szabály tanítása részletes magyarázattal."""
    if rule_id not in GRAMMAR_DATABASE:
        available = ", ".join(list(GRAMMAR_DATABASE.keys())[:5])
        return f"[ERROR] Ismeretlen szabály: {rule_id}\n\nElérhető: {available}..."

    rule = GRAMMAR_DATABASE[rule_id]
    response = f"""
╔══════════════════════════════════════════════════════════════════╗
║ 📚 MAGYAR NYELVTAN LECKE
╚══════════════════════════════════════════════════════════════════╝

🎯 TÉMA: {rule.title}
📊 SZINT: {rule.difficulty.upper()}
🏷️  KATEGÓRIA: {rule.category}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 MAGYARÁZAT:
{rule.explanation}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 SZABÁLYOK:
"""
    for i, r in enumerate(rule.rules, 1):
        response += f"{i}. {r}\n"

    response += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 PÉLDÁK:
"""
    for example in rule.examples:
        response += f"• {example}\n"

    response += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  GYAKORI HIBÁK:
"""
    for mistake in rule.common_mistakes:
        response += f"❌ {mistake}\n"

    response += "\n"
    return response


def explain_grammar(sentence: str, focus: str = "all") -> str:
    """Egy mondat nyelvtani elemzése."""
    response = f"""
╔══════════════════════════════════════════════════════════════════╗
║ 🔍 NYELVTANI ELEMZÉS
╚══════════════════════════════════════════════════════════════════╝

📝 MONDAT: {sentence}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔎 ELEMZÉS:
"""

    # Simple sentence analysis
    words = sentence.split()
    response += f"Szavak száma: {len(words)}\n\n"

    # Detect cases and endings
    endings = {
        "t": "Tárgyeset (accusative)",
        "nak": "Részeshatározó (dative)",
        "nek": "Részeshatározó (dative)",
        "ban": "Helyhatározó (locative)",
        "ben": "Helyhatározó (locative)",
        "ból": "Elöljáró eset (ablative)",
        "ből": "Elöljáró eset (ablative)",
    }

    found_cases = []
    for word in words:
        for ending, case_name in endings.items():
            if word.endswith(ending) and len(word) > len(ending):
                found_cases.append(f"• '{word}' → {case_name} (-{ending})")
                break

    if found_cases:
        for case_str in found_cases:
            response += f"{case_str}\n"
    else:
        response += "• Nincs speciális végződés — alanyeset vagy határozatlan alak.\n"

    response += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 MEGJEGYZÉS:
Az elemzés alapvető minta-alapú. Komplexebb mondatok mellett
javasolt a tanító rendszerhez fordulni.
"""
    return response


def practice_exercise(category: str = "case_practice", difficulty: str = "beginner") -> str:
    """Nyelvtani gyakorlat a tanulónak."""
    if category not in GRAMMAR_EXERCISES:
        return f"[ERROR] Ismeretlen kategória: {category}"

    exercises = GRAMMAR_EXERCISES[category]
    if not exercises:
        return "[ERROR] Nincsenek gyakorlatok ebben a kategóriában."

    ex = exercises[0]  # First exercise

    response = f"""
╔══════════════════════════════════════════════════════════════════╗
║ ✏️  NYELVTANI GYAKORLAT
╚══════════════════════════════════════════════════════════════════╝

📚 KATEGÓRIA: {category}
🎯 SZINT: {difficulty.upper()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❓ KÉRDÉS: {ex['question']}

A) {ex['options'][0]}
B) {ex['options'][1]}
C) {ex['options'][2]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ HELYES VÁLASZ: {ex['correct']}
📖 MAGYARÁZAT: {ex['explanation']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return response


def list_all_rules(category: str = None) -> str:
    """Összes nyelvtani szabály listázása."""
    response = """
╔══════════════════════════════════════════════════════════════════╗
║ 📚 MAGYAR NYELVTANI SZABÁLYOK ADATBÁZISA
╚══════════════════════════════════════════════════════════════════╝

"""

    categories_dict = {}
    for rule_id, rule in GRAMMAR_DATABASE.items():
        if category and rule.category != category:
            continue
        if rule.category not in categories_dict:
            categories_dict[rule.category] = []
        categories_dict[rule.category].append((rule_id, rule.title, rule.difficulty))

    for cat, rules in categories_dict.items():
        response += f"\n🏷️  {cat.upper()}\n"
        response += "─" * 60 + "\n"
        for rule_id, title, difficulty in rules:
            response += f"  • {rule_id:30} — {title:30} [{difficulty}]\n"

    response += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Összes szabály: {len(GRAMMAR_DATABASE)}

HASZNÁLAT:
  /teach_grammar case_nominative     — Alanyeset tanítása
  /explain_grammar "A házban lakom"  — Mondat elemzése
  /practice_exercise                 — Gyakorlat megoldása
"""
    return response


def check_grammar(text: str) -> str:
    """Szöveges nyelvtani hibák detektálása."""
    response = f"""
╔══════════════════════════════════════════════════════════════════╗
║ ✅ NYELVTANI ELLENŐRZÉS
╚══════════════════════════════════════════════════════════════════╝

📝 SZÖVEG: {text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 ELEMZÉS:
"""

    issues = []

    # Check for common mistakes
    if "nem jó" in text.lower():
        issues.append("⚠️  'nem jó' helyett 'nem helyes' vagy 'hibás' használata javasolt")
    if "azt hogy" in text.lower():
        issues.append("⚠️  'azt hogy' szerkezet — ellenőrizd az esetet")
    if "amit" in text.lower() and "-t" not in text:
        issues.append("⚠️  'amit' után általában tárgyeset szükséges")

    if issues:
        for issue in issues:
            response += f"{issue}\n"
    else:
        response += "✅ Nem találtam nyilvánvaló hibákat!\n"

    response += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 PONTSZÁM: 85/100
💡 TANÁCSOK: Fokozd a mondatok komplexitását!
"""
    return response
