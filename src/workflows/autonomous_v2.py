"""
🤖 AUTONOMOUS MODE – FRANZ (v2.0)
========================================
Implementáció a kért specifikáció alapján:
- PLAN-EXECUTE-VERIFY-REFLECT-IMPROVE ciklus
- Strukturált JSON döntésnapló
- Self-healing (max 5 retry)
- Autonóm döntéshozatal
"""

import datetime
import json
import os
import time
import traceback
from typing import Any, Dict, List, Optional

from src.llm import llm_gateway, parse_tool_calls, strip_tool_blocks
from src.security import log_event
from src.memory.structured import StructuredKB
from src.tools import AGENT_TOOLS, exec_tool
from src.config import cfg
from src.ui.display import (
    display_welcome, 
    display_step_header, 
    display_action, 
    display_result, 
    display_think_start, 
    display_task_done,
    console
)
from rich.markdown import Markdown

# Konfiguráció
MAX_AUTONOMOUS_STEPS = 50
MAX_RETRY_PER_STEP = 5
AUTONOMOUS_LOG_DIR = "logs/autonomous"

class AutonomousAgent:
    def __init__(self, model: str = "jarvis-hu-coder:latest"):
        self.model = model
        self.history: List[Dict[str, Any]] = []
        self.decision_log: List[Dict[str, Any]] = []
        self.all_tools_used: List[str] = []
        self.current_task: Optional[str] = None
        self.start_time: Optional[float] = None
        self.steps_count = 0
        self.kb = StructuredKB() # Memória integráció
        
        # Létrehozzuk a log könyvtárat
        os.makedirs(AUTONOMOUS_LOG_DIR, exist_ok=True)

    def _log_decision(self, step_type: str, action: str, reason: str, result: str, notes: str = ""):
        """Strukturált JSON naplózás a specifikáció szerint."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "step": step_type,
            "action": action,
            "reason": reason,
            "result": result,
            "notes": notes
        }
        self.decision_log.append(entry)
        
        # Mentés fájlba is (folyamatosan frissítve)
        log_file = os.path.join(AUTONOMOUS_LOG_DIR, f"decision_log_{self.start_time_str}.json")
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(self.decision_log, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log_event("AUTONOMOUS_LOG_ERROR", str(e))

    def _build_system_prompt(self, task: str) -> str:
        tools_block = "\n".join(f"  - {k}: {v}" for k, v in AGENT_TOOLS.items())
        
        # RAG: korábbi hasonló feladatok/hibák lekérése
        relevant_memories = self.kb.search(task, tag="agent")
        memory_context = ""
        if relevant_memories:
            memory_context = "\nKORÁBBI TAPASZTALATOK:\n"
            for m in relevant_memories[:3]:
                val = m.get("value", {})
                status = "SIKERES" if val.get("success") else "SIKERTELEN"
                memory_context += f"- Feladat: {val.get('task')}\n  Eredmény: {status}\n  Összegzés: {val.get('summary')}\n"

        return (
            "Te vagy Franz, egy AUTONÓM AI ágens (Senior Developer + DevOps).\n"
            "A feladatod, hogy emberi beavatkozás nélkül, önállóan oldj meg komplex problémákat.\n\n"
            "SZABÁLYOK:\n"
            "1. Dolgozz folyamatosan, ne várj user inputra minden lépésnél.\n"
            "2. Hozz saját döntéseket a legjobb tudásod alapján.\n"
            "3. Csak akkor állj meg, ha kész vagy, vagy ha kritikus adat hiányzik (pl. API kulcs).\n"
            "4. Kövesd a PLAN-EXECUTE-VERIFY-REFLECT-IMPROVE ciklust.\n\n"
            "TOOL HASZNÁLAT:\n"
            "Hívj eszközöket az alábbi formátumban:\n"
            "```tool\n"
            "{\"tool\": \"tool_name\", \"args\": {\"arg1\": \"val1\"}, \"reason\": \"miért ezt teszed\", \"expected_outcome\": \"mit vársz tőle\"}\n"
            "```\n\n"
            f"ELÉRHETŐ ESZKÖZÖK:\n{tools_block}\n\n"
            f"{memory_context}\n"
            "MINDEN lépés után elemezd az eredményt (REFLECT) és javíts ha kell (IMPROVE).\n"
            "Ha végeztél, hívd a `task_done` eszközt egy összefoglalóval."
        )

    def run(self, task: str):
        """Az autonóm ciklus futtatása."""
        self.current_task = task
        self.start_time = time.time()
        self.start_time_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.steps_count = 0
        self.history = [{"role": "system", "content": self._build_system_prompt(task)}]
        self.history.append({"role": "user", "content": f"FELADAT: {task}\nIndulj! Kezdd a tervezéssel (PLAN)."})

        display_welcome()
        console.print(f"\n[bold cyan]CÉL:[/bold cyan] {task}\n")

        while self.steps_count < MAX_AUTONOMOUS_STEPS:
            self.steps_count += 1
            display_step_header(self.steps_count, MAX_AUTONOMOUS_STEPS)
            
            try:
                # 1. GENERÁLÁS (Gondolkodás + Tool választás)
                with display_think_start():
                    response = llm_gateway.chat(self.history, task_type="code")
                
                if not response:
                    console.print("[bold red]Hiba: Üres válasz az LLM-től.[/bold red]")
                    break

                # Megjelenítjük a gondolkodást (ha nem tool hívás az egész)
                if response.strip():
                    console.print(Markdown(strip_tool_blocks(response)))

                # Kivonjuk a tool hívásokat
                tool_calls = parse_tool_calls(response)
                
                # Ha nincs tool hívás, de nem is mondta ki hogy kész (és nem hívta a task_done-t)
                if not tool_calls:
                    if "task_done" in response.lower() or "kész vagyok" in response.lower():
                        print("\033[92mÚgy tűnik, a feladat elkészült.\033[0m")
                        break
                    else:
                        # Kérjük meg, hogy használjon toolt vagy tervezzen
                        self.history.append({"role": "assistant", "content": response})
                        self.history.append({"role": "user", "content": "Kérlek használj eszközöket a lépések végrehajtásához, vagy ha végeztél, hívd a `task_done` eszközt."})
                        continue

                # 2. VÉGREHAJTÁS (EXECUTE)
                self.history.append({"role": "assistant", "content": response})
                
                # Egy iterációban több toolt is hívhat, de mi sorban futtatjuk
                all_results = []
                for tc in tool_calls:
                    tool_name = tc.get("tool")
                    args = tc.get("args", {})
                    reason = tc.get("reason", "Nincs megadva")
                    expected = tc.get("expected_outcome", "Siker")

                    display_action(tool_name, reason)
                    self.all_tools_used.append(tool_name)

                    # Végrehajtás
                    # Itt bevezetünk egy retry logikát bizonyos hibákra
                    retry_count = 0
                    result = None
                    last_exc = None
                    
                    while retry_count < MAX_RETRY_PER_STEP:
                        try:
                            result = exec_tool(tool_name, args)
                            break
                        except Exception as e:
                            retry_count += 1
                            last_exc = e
                            print(f"\033[93m[RETRY {retry_count}/{MAX_RETRY_PER_STEP}] Hiba: {e}\033[0m")
                            time.sleep(1)

                    if result is None:
                        result = f"[CRITICAL ERROR] Failed after {MAX_RETRY_PER_STEP} retries. Last error: {last_exc}"
                        status = "error"
                    else:
                        status = "success" if "[ERROR]" not in str(result) else "partial_fail"

                    display_result(status, str(result))

                    # 3. NAPLÓZÁS (Logic Log)
                    self._log_decision(
                        step_type="EXECUTE", # A ciklus része
                        action=f"{tool_name}({args})",
                        reason=reason,
                        result=status,
                        notes=str(result)[:500] 
                    )

                    all_results.append(f"Tool: {tool_name}\nResult:\n{result}")
                    
                    if tool_name == "task_done":
                        summary = args.get("summary", "Befejezve.")
                        display_task_done(summary)
                        
                        # Memória mentése (Phase D.3 log_agent_session-t használva)
                        all_tools = [tc.get("tool") for tc in tool_calls] # Ez csak az utolsó lépés, nem jó
                        # Inkább gyűjtsük a neveket a futás során
                        
                        self.kb.log_agent_session(
                            task=self.current_task,
                            steps=self.steps_count,
                            tools_used=self.all_tools_used,
                            success=True,
                            summary=summary
                        )
                        return True

                # Visszacsatolás az LLM felé (VERIFY / REFLECT input)
                combined_result = "\n---\n".join(all_results)
                self.history.append({"role": "user", "content": f"EREDMÉNYEK:\n{combined_result}\n\nMost jöhet a VERIFY és REFLECT fázis. Ha hibát látsz, jöhet az IMPROVE. Ha minden jó, haladj tovább a következő lépésre."})

            except KeyboardInterrupt:
                print("\n\033[93mAutonóm mód megszakítva a felhasználó által.\033[0m")
                break
            except Exception as e:
                print(f"\033[91mVáratlan hiba: {e}\033[0m")
                traceback.print_exc()
                break

        if self.steps_count >= MAX_AUTONOMOUS_STEPS:
            print("\033[91mElértem a maximális lépésszámot (50). Leállok.\033[0m")
        
        return False

def start_autonomous_task(task: str, model: str = "jarvis-hu-coder:latest"):
    agent = AutonomousAgent(model=model)
    return agent.run(task)
