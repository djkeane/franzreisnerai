import sys
import os
sys.path.append(os.getcwd())
from src.workflows.autonomous_v2 import AutonomousAgent
import asyncio

async def main():
    task = """
Tesztindítás:
1. Ellenőrizd, hogy a Docker telepítve van-e a gépen (Mac).
2. Ha nincs, próbáld meg telepíteni a 'brew install --cask docker' parancsal vagy javasolj alternatívát (pl. colima). 
   FIGYELEM: Ha a Docker Desktop telepítése túl lassú vagy interaktív lenne, próbáld a 'brew install colima docker' utat.
3. Miután a Docker elérhető, készíts egy Docker környezetet (Dockerfile + docker-compose.yaml ha kell).
4. Ebben a környezetben készíts 3 különböző programozási feladatot (pl. egy Python web szerver, egy Node.js script, és egy egyszerű C++ hello world).
   Minden feladat külön állományban legyen és fusson le a konténerben.
5. Ellenőrizd a futást. Ha hiba van, elemezd és javítsd magad (Franz ágens).
6. Az egész folyamatról készíts részletes jelentést a végén.
"""
    # Kényszerítjük a 'code' task típusra a stabilabb modellekért (Groq/Ollama)
    agent = AutonomousAgent()
    agent.run(task)

if __name__ == "__main__":
    asyncio.run(main())
