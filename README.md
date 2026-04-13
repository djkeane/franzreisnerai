# Franz – Agentic Terminal AI

**v4.0** | Fejlesztő: **DömösAiTech 2026**

Franz egy offline-first, biztonságos, bővíthető terminál AI-ügynök.  
Helyi Ollama-modellekkel fut, Gemini-fallback-kel, és képes önállóan eszközöket (tools) hívni a feladatok elvégzéséhez – bash, fájlkezelés, git, web – mindezt agentic loop-ban.

---

## Funkciók

### v4.0 – Agentic Terminal AI (legújabb)
| Funkció | Leírás |
|---------|--------|
| **Agentic loop** | Az LLM önállóan hívhat eszközöket (bash, read_file, write_file, list_dir, git, web_fetch) és iterál, amíg a feladat kész |
| **Streaming válasz** | Valós idejű token-streaming Ollama-ból – azonnal látható a válasz |
| **Rich UI** | Markdown rendering, szintaxis-kiemelés, panel-keretek (`rich` könyvtár) |
| **Readline integráció** | Nyílbillentyű-navigáció, `↑↓` előzmény, `Tab` parancs-kiegészítés, 2000 soros history fájl |
| **Multi-line input** | `\` a sor végén = folytatás; ` ``` ` = paste-mód blokk |
| **Veszélyes parancs detektálás** | rm -rf, dd, mkfs, fork-bomb stb. automatikusan blokkolva |
| **Rendszer-kontextus** | CWD, CPU/RAM, git-branch+státusz automatikusan bekerül a system prompt-ba |
| **Súgó** | `help` parancs – teljes parancs-lista |

### v3.0 – Security Hardened
| Funkció | Leírás |
|---------|--------|
| **Multi-topic memória** | Minden téma saját `.jsonl` fájlban (`~/Franz/memory/`) |
| **Snapshot / Revert** | `snapshot` → időbélyegzett backup; `revert:` → visszaállítás |
| **Keresés** | `search: <kulcsszó> [role]` – gyors keresés a topic-memóriában |
| **Agent-csapat** | `dev:` → DeveloperAgent, `debug:` → DebugAgent – saját system-prompt |
| **Plugin/Hook rendszer** | `plugins/` könyvtárban Python-modulok (`hook(name, args)`) |
| **Whitelist shell** | `run:`-parancs csak whitelist-binárisokat enged |
| **Resource-limit** | CPU-s + memória-limit child-processzekre |
| **Privilege-drop** | Root esetén `nobody`-ra vált |
| **Webhook alert** | DENIED/EXCEPTION eseménynél Slack/Discord értesítés |
| **Diagnosztika** | `diagnosztizál` – könyvtár-jogok, config, Ollama/Gemini státusz |
| **Több Ollama-endpoint** | Vesszővel elválasztott URL-lista, sorban próbálja |

---

## Telepítés

```bash
# 1. Könyvtár
mkdir -p ~/Franz/{memory,logs,agents,plugins}
chmod 700 ~/Franz

# 2. Python-függőségek
pip3 install --user requests psutil rich google-genai

# 3. Indítás
python3 ~/Franz/franz.py
```

### Alias (opcionális)
```bash
echo 'alias franz="python3 ~/Franz/franz.py"' >> ~/.zshrc
source ~/.zshrc
```

---

## Könyvtár-struktúra

```
~/Franz/
├── franz.py               # fő szkript (v4.0 – agentic + streaming)
├── franz.cfg              # konfiguráció
├── franz_autopush.sh      # auto git push script
├── .history               # readline history
├── memory/
│   ├── .active_topic
│   ├── default.jsonl
│   └── dev_*.jsonl / debug_*.jsonl
├── logs/
│   └── session_YYYYMMDD_HHMMSS.log
├── agents/
│   ├── __init__.py        # BaseAgent
│   ├── developer_agent.py
│   └── debug_agent.py
└── plugins/               # hook-modulok
```

---

## Konfiguráció (`franz.cfg`)

```ini
[agent]
max_tool_steps = 10     ; max iteráció az agentic loop-ban
streaming = true         ; valós idejű streaming
confirm_bash = false     ; bash-megerősítés ki/be

[ollama]
url = http://localhost:11434,http://localhost:11435
default_model = jarvis-hu-coder:latest
fallback_models = jarvis-hu:latest,cronic:latest
timeout = 60

[gemini]
model = gemini-1.5-flash

[security]
whitelist = ls,cat,git,curl,ps,du,netstat,ping,wget,docker,kubectl,systemctl
cpu_soft = 5
cpu_hard = 10
mem_limit_mb = 200
alert_webhook =          ; Slack/Discord webhook URL

[DeveloperAgent]
display_name = Developer Agent
description = Python/Go/Node.js kód, Dockerfile, unit-test, Git
topic_prefix = dev_
model = jarvis-hu-coder:latest

[DebugAgent]
display_name = Debug Agent
description = Log-elemzés, stack-trace, systemd, Docker/k8s debug
topic_prefix = debug_
model = jarvis-hu:latest
```

---

## Parancsok

### Chat
| Parancs | Leírás |
|---------|--------|
| `<kérdés>` | AI válasz + automatikus tool-hívás ha szükséges |
| Sor vége `\` | Következő sor folytatás |
| ` ``` ` + Enter | Paste-mód (` ``` ` zárja) |

### Agensek
| Parancs | Leírás |
|---------|--------|
| `dev: <feladat>` | Developer Agent – kódgenerálás |
| `debug: <feladat>` | Debug Agent – hibaelemzés |

### Topic / Memória
| Parancs | Leírás |
|---------|--------|
| `topic: <név>` | Topic váltás / létrehozás |
| `topics` | Topic-ok listája |
| `reset:` | Aktuális topic törlése |
| `snapshot` | Backup készítés |
| `revert: <fájl>` | Visszaállítás korábbi állapotra |
| `search: <szó> [role]` | Keresés a memóriában |

### Pluginek & Rendszer
| Parancs | Leírás |
|---------|--------|
| `hook: <név> <args>` | Plugin hook hívása |
| `hooks` | Betöltött hook-ok listája |
| `diagnosztizál` | Rendszer-diagnosztika |
| `help` | Súgó |
| `exit` / `quit` | Kilépés |

---

## Automatikus eszközök (agentic loop)

Az LLM ezeket hívhatja önállóan a feladatok elvégzéséhez:

| Eszköz | Argumentumok | Leírás |
|--------|-------------|--------|
| `bash` | `command: str` | Bash parancs (veszélyes minták blokkolva) |
| `read_file` | `path: str` | Fájl beolvasása (max 500 sor) |
| `write_file` | `path: str, content: str` | Fájl létrehozása/felülírása |
| `list_dir` | `path: str` | Könyvtár listázása mérettel |
| `git` | `args: str` | Git parancs |
| `web_fetch` | `url: str` | Weboldal szöveges tartalma |

---

## Plugin fejlesztés

Hozz létre `~/Franz/plugins/my_plugin.py`-t:

```python
def hook(name: str, args: str) -> str:
    # args = felhasználótól kapott string
    return f"[{name}] Feldolgozva: {args}"
```

Induláskor automatikusan betöltődik, `hook: my_plugin <args>`-szal hívható.

---

## Auto-push (GitHub)

A `franz_autopush.sh` + `launchd` automatikusan pusholja a változásokat:

```bash
# Állapot
launchctl list | grep franzreisnerai

# Log
tail -f ~/Franz/logs/autopush.log
```

**Repó:** [github.com/djkeane/franzreisnerai](https://github.com/djkeane/franzreisnerai)

---

*DömösAiTech 2026 – Minden jog fenntartva*
