import sys
import os
import time

# Hozzáadjuk a Franz gyökeret a pathhoz
sys.path.append("/Users/domoslaszlo/Franz")

from src.workflows.autonomous_v2 import start_autonomous_task
from src.ui.display import console

def test_new_features():
    task = "Mutasd meg a jelenlegi könyvtár struktúráját a `tree` eszközzel, majd keress rá a `src/tools.py` fájlban a 'bash' szóra a `grep_content` eszközzel."
    
    console.clear()
    console.print("[bold yellow]🧪 FRANZ V2.1 TERMINÁL TESZT[/bold yellow]")
    console.print("-" * 40)
    
    try:
        # Futtatjuk a feladatot
        # A jarvis-hu-coder modellt használjuk a legjobb eredményért
        success = start_autonomous_task(task, model="jarvis-hu-coder:latest")
        
        if success:
            console.print("\n[bold green]✅ Teszt sikeresen befejeződött![/bold green]")
        else:
            console.print("\n[bold red]❌ Teszt sikertelen vagy időtúllépés.[/bold red]")
            
    except Exception as e:
        console.print(f"\n[bold red]HIBA A TESZT SORÁN:[/bold red] {e}")

if __name__ == "__main__":
    test_new_features()
