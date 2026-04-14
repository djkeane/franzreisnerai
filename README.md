# Franz – Agentic Terminal AI

**v5.0** | Fejlesztő: **DömösAiTech 2026** | [GitHub](https://github.com/djkeane/franzreisnerai)

Franz egy offline-first, biztonságos, moduláris terminál AI-ügynök.  
Helyi Ollama-modellekkel fut (Gemini/Claude fallback-kel), és képes önállóan eszközöket hívni – bash, fájlkezelés, git, web – agentic loop-ban.

---

## Funkciók

### v5.0 – Moduláris Agentic AI
| Funkció | Leírás |
|---------|--------|
| **Moduláris architektúra** | `src/` csomag: config, security, llm, memory, tools, hooks, agents, diagnostics |
| **Agentic loop** | LLM önállóan hívhat eszközöket és iterál, amíg a feladat kész |
| **Streaming válasz** | Valós idejű token-streaming Ollama-ból (`StreamParser` osztály) |
| **LLM fallback lánc** | Ollama → Ollama fallback modellek → Gemini → Claude |
| **Multi-topic memória** | Minden téma saját JSONL fájlban (`memory/`) |
| **Snapshot / Revert** | Időbélyegzett backup + visszaállítás |
| **Keresés** | Kulcsszó-keresés a topic-memóriában |
| **AgentRegistry** | Dinamikus agens-betöltés config-ból |
| **Agensek** | `DeveloperAgent`, `DebugAgent` – saját system prompttal |
| **Plugin/Hook rendszer** | `plugins/` könyvtárból automatikusan betöltött hook-ok |
| **Biztonság** | Whitelist, veszélyes parancs detektálás, resource limit, privilege drop |
| **Docker támogatás** | `docker-compose.yml` + `Dockerfile` multi-stage build |
| **Rich UI** | Markdown rendering, szintaxis-kiemelés (`rich` könyvtár) |
| **Readline** | `↑↓` előzmény, Tab kiegészítés, 2000 soros history |
| **Beépített eszközök** | `ls:`, `cat:`, `du:`, `ps:`, `top`, `net:`, `svc:`, `docker:`, `kubectl:`, `run:` |
| **confirm_bash** | Opcionális megerősítés bash tool-hívásoknál |

---

## Telepítés

### Helyi futtatás
```bash
# 1. Klónozás
git clone https://github.com/djkeane/franzreisnerai.git ~/Franz
cd ~/Franz

# 2. Python-függőségek
pip3 install --user requests psutil rich google-generativeai

# 3. Indítás
python3 franz.py
```

### Docker (ajánlott)
```bash
cd ~/Franz
docker compose up -d

# Interaktív terminál
docker compose exec franz python franz.py
```

### Alias
```bash
echo 'alias franz="python3 ~/Franz/franz.py"' >> ~/.zshrc
source ~/.zshrc
```

---

## Konfiguráció (`franz.cfg`)

```ini
[ollama]
url = http://localhost:11434,http://localhost:11435
default_model = jarvis-hu-coder:latest
fallback_models = jarvis-hu:latest,cronic:latest
timeout = 15

[gemini]
model = gemini-1.5-flash

[agent]
max_tool_steps = 10
streaming = true
confirm_bash = false

[security]
whitelist = ls,cat,du,ps,top,netstat,ping,curl,wget,git,docker,kubectl,systemctl
cpu_soft = 5
cpu_hard = 10
mem_limit_mb = 200
alert_webhook =

[DeveloperAgent]
display_name = Developer Agent
description = Python/Go/Node.js kod, Dockerfile, unit-test, Git
model = jarvis-hu-coder:latest

[DebugAgent]
display_name = Debug Agent
description = Log-elemzes, stack-trace, systemd, Docker/k8s debug
model = jarvis-hu:latest
```

---

## Konyvtar-struktura

```
~/Franz/
├── franz.py               # belepesi pont → src.cli:main()
├── franz.cfg              # konfiguracid
├── franz_autopush.sh      # auto git push script
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── cli.py             # REPL fohurok
│   ├── config.py          # konfiguracid betolto
│   ├── llm.py             # LLM wrapper (Ollama/Gemini/Claude)
│   ├── memory.py          # JSONL memoria kezelo
│   ├── security.py        # whitelist, resource limit, logging
│   ├── tools.py           # tool executor + beepitett parancsok
│   ├── hooks.py           # plugin betolto
│   ├── diagnostics.py     # rendszer-diagnosztika
│   └── agents/
│       ├── __init__.py    # AgentRegistry
│       ├── base_agent.py  # BaseAgent ABC
│       ├── developer_agent.py
│       └── debug_agent.py
├── memory/                # tema JSONL fajlok
├── logs/                  # session logok
└── plugins/               # sajat hook pluginok
```

---

## Parancsok

| Parancs | Leiras |
|---------|--------|
| `/help` | Sugo |
| `/exit` | Kilepes |
| `/topic <nev>` | Tema valtas |
| `/topics` | Temak listaja |
| `/snapshot` | Memoria mentese |
| `/revert <bak>` | Visszaallitas |
| `/search <kulcsszo>` | Kereses a memoriban |
| `/agents` | Agensek listaja |
| `/agent <Nev> <feladat>` | Agens inditasa |
| `/diag` | Diagnosztika |
| `ls:<path>` | Konyvtar lista |
| `docker:<args>` | Docker parancs |
| `kubectl:<args>` | kubectl parancs |

---

## Uj agens hozzaadasa

1. Hozz letre `src/agents/myagent.py` fajlt `MyAgent(BaseAgent)` osztalyyal
2. Add hozza a `franz.cfg`-hez `[MyAgent]` szekciont
3. Franz automatikusan betolti indulaskor

---

## Licenc

MIT (c) DomosAiTech 2026
