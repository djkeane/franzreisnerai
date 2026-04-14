"""Scraping + tanulás pipeline — webről tudást gyűjt és beépít."""

from __future__ import annotations

import os
import re
from typing import Callable
from urllib.parse import quote

from src.learn import learn
from src.security import log_event


def _fetch_duckduckgo(query: str, max_results: int = 5) -> list[str]:
    """
    DuckDuckGo lite HTML keresés — nem JS, sima szöveges linkek.
    Visszaadás: ["https://...", "https://...", ...]
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        links = []
        for a in soup.find_all("a", class_="result__url"):
            href = a.get("href")
            if href and href.startswith("http"):
                links.append(href)
                if len(links) >= max_results:
                    break
        return links
    except Exception as exc:
        log_event("DUCKDUCKGO_ERROR", str(exc))
        return []


def _scrape_url(url: str, max_chars: int = 4000) -> str | None:
    """
    Egyszerű URL scraping: requests + BeautifulSoup.
    Visszaadás: szöveges tartalom vagy None ha hiba.
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Eltávolít script/style tagokat
        for tag in soup(["script", "style"]):
            tag.decompose()

        # Szöveg kibontás
        text = soup.get_text(separator="\n", strip=True)
        # Szóközök normalizálása
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]

    except Exception as exc:
        log_event("SCRAPE_ERROR", f"{url}: {exc}")
        return None


def _summarize(text: str, llm_fn: Callable[[str], str], max_words: int = 500) -> str:
    """
    LLM-mel összefoglalja a szöveget max_words szóig.
    """
    if len(text) < 100:
        return text

    prompt = f"""Foglalj össze egy szöveget {max_words} szó alatt, lényegre törően:

{text[:2000]}

ÖSSZEFOGLALÁS:"""

    try:
        summary = llm_fn(prompt)
        return summary.strip()[:max_words * 5]  # ~5 char/szó
    except Exception as exc:
        log_event("SUMMARIZE_ERROR", str(exc))
        return text[:max_words * 5]


def auto_learn(
    topic_or_url: str,
    llm_fn: Callable[[str], str] | None = None,
    max_pages: int = 3,
) -> int:
    """
    Webes keresés, scraping, összefoglalás, tanulás.

    Argumentumok:
        topic_or_url: keresési téma vagy konkrét URL
        llm_fn: LLM függvény (összefoglaláshoz); ha None, gateway-t használ
        max_pages: max scrapeolható oldal

    Visszaadás:
        tárolt tények száma
    """
    if llm_fn is None:
        from src.llm import llm_gateway
        llm_fn = lambda p: llm_gateway.chat(
            [{"role": "user", "content": p}],
            task_type="research"
        )

    topic = topic_or_url.split("/")[-1] if "/" in topic_or_url else topic_or_url
    log_event("AUTO_LEARN_START", f"{topic[:50]}")

    stored = 0

    # 1. URL vagy keresés?
    if topic_or_url.startswith(("http://", "https://")):
        urls = [topic_or_url]
    else:
        urls = _fetch_duckduckgo(topic, max_results=max_pages)

    if not urls:
        log_event("AUTO_LEARN_NO_URLS", topic)
        return 0

    # 2. Scrape + tanulás
    for url in urls[:max_pages]:
        text = _scrape_url(url)
        if not text:
            continue

        # Összefoglalás
        summary = _summarize(text, llm_fn, max_words=500)
        if not summary or len(summary) < 20:
            continue

        # Tanulás
        try:
            learn(
                text=summary,
                source=url,
                tags=["auto-learned", topic],
            )
            stored += 1
            log_event("AUTO_LEARNED", f"{url[:60]}")
        except Exception as exc:
            log_event("LEARN_STORAGE_ERROR", str(exc))

    log_event("AUTO_LEARN_DONE", f"{topic}: {stored} tény")
    return stored


def enable_playwright() -> bool:
    """
    Playwright engedélyezése: ha telepítve van és PLAYWRIGHT_ENABLED=1.
    Ezzel később DOMi interakció és JS-es oldalak lehetségesek.
    """
    if not os.getenv("PLAYWRIGHT_ENABLED", "").lower() in ("1", "true"):
        return False

    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        log_event("PLAYWRIGHT_MISSING", "pip install playwright")
        return False
