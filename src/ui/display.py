from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box
import datetime

console = Console()

def display_welcome():
    welcome_text = """
# 🤖 FRANZ AI - AUTONÓM TERMINÁL
---
Verzió: 2.1 (Claude Code-szerű hatékonysággal)

### Képességek:
- **PLAN:** Automatizált projekt tervezés
- **EXECUTE:** Valós idejű kód generálás és shell futtatás
- **VERIFY:** Integrált tesztelés és hibakeresés
- **REFLECT:** Folyamatos öntanulás és optimalizálás
    """
    console.print(Panel(Markdown(welcome_text), title="[bold blue]Franz AI[/bold blue]", border_style="blue", box=box.ROUNDED))

def display_step_header(step_num, max_steps):
    console.print(f"\n[bold black on white] LÉPÉS {step_num}/{max_steps} [/bold black on white]")

def display_action(action, reason):
    table = Table(show_header=False, box=box.MINIMAL, padding=(0, 1))
    table.add_row("[bold cyan]Akció:[/bold cyan]", action)
    table.add_row("[bold cyan]Indoklás:[/bold cyan]", reason)
    console.print(table)

def display_result(status, result_text):
    color = "green" if status == "success" else "yellow" if status == "partial_fail" else "red"
    title = f"[bold {color}]EREDMÉNY ({status.upper()})[/bold {color}]"
    
    # Ha a kimenet túl hosszú, rövidítjük vagy syntax highlightoljuk
    if result_text.startswith("```"):
        display_content = Markdown(result_text)
    else:
        display_content = result_text[:2000] + ("..." if len(result_text) > 2000 else "")
        
    console.print(Panel(display_content, title=title, border_style=color))

def display_think_start():
    return Live(Progress(SpinnerColumn(), TextColumn("[bold blue]Franz gondolkodik..."), transient=True))

def display_task_done(summary):
    console.print(Panel(f"[bold green]✅ FELADAT KÉSZ:[/bold green]\n{summary}", border_style="green", box=box.DOUBLE))
