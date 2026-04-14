#!/usr/bin/env python3
"""
FRANZ v7.5 COMPREHENSIVE CODING TEST SUITE
Multi-domain code generation and analysis
"""
import sys
import os
sys.path.insert(0, '/Users/domoslaszlo/Franz')
os.chdir('/Users/domoslaszlo/Franz')

from src.llm.gateway import LLMGateway
from src.classifier import classify
import time
import json

# ════════════════════════════════════════════════════════════════════════════════
# TEST SUITE
# ════════════════════════════════════════════════════════════════════════════════

CODING_TESTS = [
    {
        "id": "TEST_001",
        "name": "Fibonacci Generator (Algorithm)",
        "task": "Írj egy optimalizált Python függvényt amely kiszámítja az N-edik Fibonacci számot memoizációval. Magyarázd el az algoritmust lépésről lépésre.",
        "expected_keywords": ["fibonacci", "memoization", "recursion", "cache", "dynamic"],
        "category": "algorithms",
    },
    {
        "id": "TEST_002", 
        "name": "REST API Endpoint (Backend)",
        "task": "Tervezd meg és implementálj egy FastAPI endpoint-et amely felhasználókat kezel (GET, POST, DELETE). Magyarázd meg az error handling stratégiáját.",
        "expected_keywords": ["fastapi", "endpoint", "get", "post", "delete", "error", "validation"],
        "category": "backend",
    },
    {
        "id": "TEST_003",
        "name": "Database Schema Design",
        "task": "Tervezz meg egy PostgreSQL sémát egy e-commerce rendszerhez. Definiálj users, products, orders táblákat foreign key relációkkal. Magyarázd meg az indexing stratégiáját.",
        "expected_keywords": ["create table", "foreign key", "index", "primary key", "constraint"],
        "category": "database",
    },
    {
        "id": "TEST_004",
        "name": "React Component (Frontend)",
        "task": "Írj egy React komponenst amely dinamikus todo listát kezel state-vel, localStorage-val szinkronizálja az adatokat. Kell error boundary és loading state.",
        "expected_keywords": ["usestate", "useeffect", "localstorage", "map", "component", "jsx"],
        "category": "frontend",
    },
    {
        "id": "TEST_005",
        "name": "System Architecture Design",
        "task": "Tervezz meg egy mikroszolgáltatás architektúrát egy nagy léptékű chat platformhoz. Magyarázd meg a service discovery, load balancing, és failure handling stratégiát.",
        "expected_keywords": ["microservices", "architecture", "kubernetes", "scaling", "failover", "api gateway"],
        "category": "architecture",
    },
]

# ════════════════════════════════════════════════════════════════════════════════
# TESTING FRAMEWORK
# ════════════════════════════════════════════════════════════════════════════════

class CodeQualityAnalyzer:
    """Analyzes code quality across multiple dimensions"""
    
    def __init__(self):
        self.gateway = LLMGateway()
    
    def analyze_response(self, response: str, test: dict) -> dict:
        """Analyze code quality"""
        metrics = {
            "completeness": 0,
            "explanation_quality": 0,
            "code_correctness": 0,
            "best_practices": 0,
            "overall_score": 0,
        }
        
        # Check for expected keywords
        response_lower = response.lower()
        keyword_hits = sum(1 for kw in test["expected_keywords"] if kw in response_lower)
        metrics["completeness"] = min(100, (keyword_hits / len(test["expected_keywords"])) * 100)
        
        # Check for explanation markers
        has_explanation = any(x in response_lower for x in ["magyaráz", "explain", "lépés", "step", "miért", "why"])
        metrics["explanation_quality"] = 80 if has_explanation else 30
        
        # Check code structure
        has_code = "```" in response or "def " in response or "class " in response
        if has_code:
            proper_indentation = response.count("    ") > 0
            has_comments = "#" in response or "//" in response
            metrics["code_correctness"] = 70 if proper_indentation else 40
            metrics["best_practices"] = 80 if has_comments else 50
        
        # Calculate overall score
        metrics["overall_score"] = (
            metrics["completeness"] * 0.3 +
            metrics["explanation_quality"] * 0.25 +
            metrics["code_correctness"] * 0.25 +
            metrics["best_practices"] * 0.2
        )
        
        return metrics
    
    def run_test(self, test: dict) -> dict:
        """Run a single coding test"""
        print(f"\n{'='*80}")
        print(f"🧪 {test['id']}: {test['name']}")
        print(f"{'='*80}")
        print(f"Kategória: {test['category']}")
        print(f"\n📝 Feladat:\n{test['task']}\n")
        
        start_time = time.time()
        
        # Classify task
        classification = classify(test['task'])
        print(f"✓ Task Classification: {classification.type} (agentic={classification.is_agentic})")
        
        # Generate response using gateway with auto-routing
        messages = [
            {"role": "system", "content": "Te egy szakértő szoftverfejlesztő vagy. Válaszolj részletesen, magyarázz meg mindent lépésről lépésre. Adj konkrét kódpéldákat."},
            {"role": "user", "content": test['task']}
        ]
        
        try:
            response = self.gateway.chat(
                messages=messages,
                task_type="code",  # Explicit code routing
                temperature=0.3,
                max_tokens=2048,
            )
        except Exception as e:
            response = f"[ERROR] {str(e)}"
        
        elapsed = time.time() - start_time
        
        # Analyze response
        metrics = self.analyze_response(response, test)
        
        # Display results
        print(f"\n📊 QUALITY METRICS:")
        print(f"  • Completeness:       {metrics['completeness']:.1f}%")
        print(f"  • Explanation:        {metrics['explanation_quality']:.1f}%")
        print(f"  • Code Correctness:   {metrics['code_correctness']:.1f}%")
        print(f"  • Best Practices:     {metrics['best_practices']:.1f}%")
        print(f"  • OVERALL SCORE:      {metrics['overall_score']:.1f}% ⭐")
        print(f"\n⏱️  Response Time: {elapsed:.2f}s")
        print(f"\n📄 Response Preview: {response[:200]}...")
        
        return {
            "test_id": test["id"],
            "test_name": test["name"],
            "category": test["category"],
            "metrics": metrics,
            "response_length": len(response),
            "response_time": elapsed,
            "classification": classification.type,
        }

# ════════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ════════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "="*80)
    print("🧪 FRANZ v7.5 COMPREHENSIVE CODING TEST SUITE")
    print("="*80 + "\n")
    
    analyzer = CodeQualityAnalyzer()
    results = []
    
    for test in CODING_TESTS:
        try:
            result = analyzer.run_test(test)
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed: {e}")
            results.append({
                "test_id": test["id"],
                "error": str(e),
            })
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    total_score = sum(r.get("metrics", {}).get("overall_score", 0) for r in results) / len(results)
    
    print(f"\nTotal Tests Run: {len(CODING_TESTS)}")
    print(f"Average Overall Score: {total_score:.1f}%\n")
    
    print("Category Breakdown:")
    categories = {}
    for result in results:
        cat = result.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"count": 0, "score": 0}
        categories[cat]["count"] += 1
        categories[cat]["score"] += result.get("metrics", {}).get("overall_score", 0)
    
    for cat, data in categories.items():
        avg = data["score"] / data["count"] if data["count"] > 0 else 0
        print(f"  • {cat:20} {data['count']} tests → {avg:.1f}% avg")
    
    # Detailed results
    print("\n" + "-"*80)
    print("Detailed Results:")
    print("-"*80)
    for result in results:
        if "metrics" in result:
            print(f"\n{result['test_id']:10} {result['test_name']:40} → {result['metrics']['overall_score']:.1f}%")

if __name__ == "__main__":
    main()
