
import sys
import os
sys.path.append(os.getcwd())

from src.llm.gateway import LLMGateway
from src.security import log_event

def test_smart_routing():
    gateway = LLMGateway()
    
    test_cases = [
        {"msg": "Írj egy python scriptet", "expected": "code"},
        {"msg": "Milyen lépések kellenek egy szerver telepítéshez?", "expected": "planner"},
        {"msg": "Ellenőrizd ezt a kódot hibákra", "expected": "verifier"},
        {"msg": "Szia, hogy vagy?", "expected": "hungarian"},
        {"msg": "Search for latest AI news on GitHub", "expected": "research"},
        {"msg": "What is the capital of France?", "expected": "general"}
    ]
    
    print("\n--- Smart Routing Test ---\n")
    for case in test_cases:
        messages = [{"role": "user", "content": case["msg"]}]
        task_type = gateway._classify_task(messages)
        status = "✅" if task_type == case["expected"] else "❌"
        print(f"Prompt: {case['msg']}\nResult: {task_type} (Expected: {case['expected']}) {status}\n")

if __name__ == "__main__":
    test_smart_routing()
