"""
Autonomous Agent Dependency Manager
Manages virtual environments, requirements, dependency resolution
"""

from __future__ import annotations
import subprocess
import pathlib
import re
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

from src.security import log_event


class DependencyType(Enum):
    """Dependency classification"""
    CORE = "core"  # Direct imports in code
    OPTIONAL = "optional"  # Optional features
    DEV = "dev"  # Development tools
    TESTING = "testing"  # Test frameworks


@dataclass
class Dependency:
    """Single package dependency"""
    name: str
    version: str  # "1.2.3" or ">= 2.0"
    type: DependencyType
    imported_by: List[str]  # Files that import this
    installed: bool = False


@dataclass
class RequirementsFile:
    """Parsed requirements file"""
    path: str
    dependencies: List[Dependency]
    total: int
    installed: int


@dataclass
class VirtualEnv:
    """Virtual environment info"""
    path: str
    python_version: str
    is_active: bool
    total_packages: int
    outdated_packages: int
    missing_dependencies: List[str]


# ════════════════════════════════════════════════════════════════════════════════
# DEPENDENCY MANAGER
# ════════════════════════════════════════════════════════════════════════════════

class DependencyManager:
    """
    Manage project dependencies:
    - Virtual environment creation and activation
    - Requirements file parsing
    - Dependency extraction from imports
    - Version conflict resolution
    """

    def __init__(self, project_root: str = "."):
        self.project_root = pathlib.Path(project_root)
        self.venv_path = self.project_root / ".venv"
        self.requirements_files = [
            "requirements.txt",
            "requirements-dev.txt",
            "setup.py",
            "pyproject.toml",
            "Pipfile"
        ]
        self.dependency_cache: Dict[str, Dependency] = {}

    # ── Virtual Environment ────────────────────────────────────────

    def create_venv(self, python_version: str = "3.11") -> bool:
        """Create virtual environment"""
        try:
            subprocess.run(
                [f"python{python_version}", "-m", "venv", str(self.venv_path)],
                timeout=30,
                check=True
            )
            log_event("VENV_CREATED", str(self.venv_path))
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            log_event("VENV_ERROR", f"Failed to create venv: {python_version}")
            return False

    def get_pip_executable(self) -> str:
        """Get pip executable path for current venv"""
        if pathlib.Path(self.venv_path).exists():
            pip_path = self.venv_path / "bin" / "pip"
            if pip_path.exists():
                return str(pip_path)

        return "pip"

    def is_venv_active(self) -> bool:
        """Check if virtual environment is active"""
        try:
            result = subprocess.run(
                ["python", "-m", "sys", "-c", "import sys; print(sys.prefix)"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return str(self.venv_path) in result.stdout
        except:
            return False

    def get_venv_info(self) -> Optional[VirtualEnv]:
        """Get current virtual environment info"""
        try:
            pip = self.get_pip_executable()
            result = subprocess.run(
                [pip, "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=10
            )

            packages = json.loads(result.stdout)
            total = len(packages)

            # Check for outdated
            outdated_result = subprocess.run(
                [pip, "list", "--outdated", "--format=json"],
                capture_output=True,
                text=True,
                timeout=10
            )

            outdated = len(json.loads(outdated_result.stdout))

            return VirtualEnv(
                path=str(self.venv_path),
                python_version="3.11",  # TODO: detect actual version
                is_active=self.is_venv_active(),
                total_packages=total,
                outdated_packages=outdated,
                missing_dependencies=[]
            )

        except Exception as e:
            log_event("VENV_INFO_ERROR", str(e))
            return None

    # ── Requirements Parsing ───────────────────────────────────────

    def parse_requirements_file(self, file_path: str) -> RequirementsFile:
        """Parse requirements.txt file"""
        try:
            path = self.project_root / file_path
            if not path.exists():
                return RequirementsFile(file_path, [], 0, 0)

            content = path.read_text(encoding="utf-8")
            dependencies = []

            for line in content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Parse requirement: "package>=1.0" or "package==1.2.3"
                match = re.match(r"^([a-zA-Z0-9_-]+)(.*)$", line)
                if match:
                    name = match.group(1)
                    version_spec = match.group(2).strip() or "*"

                    dep = Dependency(
                        name=name,
                        version=version_spec,
                        type=DependencyType.CORE,
                        imported_by=[],
                        installed=self._is_installed(name)
                    )
                    dependencies.append(dep)

            installed = sum(1 for d in dependencies if d.installed)
            log_event("REQUIREMENTS_PARSED", f"{file_path}: {len(dependencies)} deps")

            return RequirementsFile(file_path, dependencies, len(dependencies), installed)

        except Exception as e:
            log_event("REQUIREMENTS_ERROR", f"{file_path}: {str(e)}")
            return RequirementsFile(file_path, [], 0, 0)

    def _is_installed(self, package_name: str) -> bool:
        """Check if package is installed"""
        try:
            subprocess.run(
                ["python", "-c", f"import {package_name}"],
                capture_output=True,
                timeout=5
            )
            return True
        except:
            return False

    # ── Import Analysis ────────────────────────────────────────────

    def extract_imports(self, file_path: str) -> Set[str]:
        """Extract import statements from Python file"""
        try:
            path = self.project_root / file_path
            if not path.exists():
                return set()

            content = path.read_text(encoding="utf-8")
            imports = set()

            # Match: import X, from X import Y, from X import Y as Z
            for match in re.finditer(r"^(?:from\s+([^\s]+)\s+)?import\s+([^\n]+)", content, re.MULTILINE):
                if match.group(1):
                    imports.add(match.group(1).split(".")[0])
                for item in match.group(2).split(","):
                    item = item.strip().split(" as ")[0]
                    if item:
                        imports.add(item.split(".")[0])

            return imports

        except Exception as e:
            log_event("IMPORT_EXTRACT_ERROR", f"{file_path}: {str(e)}")
            return set()

    def scan_project_imports(self) -> Dict[str, Set[str]]:
        """Scan all Python files for imports"""
        imports_by_file = {}

        for py_file in self.project_root.rglob("*.py"):
            rel_path = str(py_file.relative_to(self.project_root))
            if ".venv" not in rel_path and "__pycache__" not in rel_path:
                imports_by_file[rel_path] = self.extract_imports(rel_path)

        log_event("PROJECT_SCAN", f"Found {len(imports_by_file)} Python files")
        return imports_by_file

    # ── Dependency Installation ────────────────────────────────────

    def install_requirements(self, file_path: str = "requirements.txt") -> bool:
        """Install dependencies from requirements file"""
        try:
            path = self.project_root / file_path
            if not path.exists():
                log_event("INSTALL_ERROR", f"{file_path} not found")
                return False

            pip = self.get_pip_executable()
            result = subprocess.run(
                [pip, "install", "-r", str(path)],
                cwd=self.project_root,
                capture_output=True,
                timeout=120
            )

            if result.returncode == 0:
                log_event("INSTALL_SUCCESS", f"Installed from {file_path}")
                return True
            else:
                log_event("INSTALL_ERROR", result.stderr.decode())
                return False

        except Exception as e:
            log_event("INSTALL_EXCEPTION", str(e))
            return False

    def install_package(self, package_name: str, version: Optional[str] = None) -> bool:
        """Install single package"""
        try:
            pip = self.get_pip_executable()
            pkg_spec = f"{package_name}{version}" if version else package_name

            result = subprocess.run(
                [pip, "install", pkg_spec],
                capture_output=True,
                timeout=60
            )

            if result.returncode == 0:
                log_event("PACKAGE_INSTALLED", package_name)
                return True

            return False

        except Exception as e:
            log_event("PACKAGE_INSTALL_ERROR", str(e))
            return False

    # ── Dependency Resolution ──────────────────────────────────────

    def find_missing_dependencies(self) -> List[str]:
        """Find missing dependencies from project imports"""
        project_imports = self.scan_project_imports()
        all_imports = set()

        for imports in project_imports.values():
            all_imports.update(imports)

        # Standard library modules to skip
        stdlib = {
            "sys", "os", "pathlib", "json", "re", "subprocess", "hashlib",
            "dataclasses", "typing", "enum", "time", "datetime", "collections",
            "itertools", "functools", "operator", "string", "io", "tempfile",
            "shutil", "glob", "fnmatch", "linecache", "pickle", "sqlite3",
            "csv", "configparser", "logging", "argparse", "getpass", "getopt",
            "platform", "curses", "threading", "multiprocessing", "concurrent",
            "asyncio", "socket", "ssl", "http", "urllib", "email", "json",
            "xml", "html", "ast", "symtable", "token", "tokenize", "inspect",
            "types", "copy", "numbers", "decimal", "fractions", "random",
            "statistics", "warnings", "unittest", "doctest", "pdb",
        }

        missing = []
        for imp in all_imports:
            if imp not in stdlib and not self._is_installed(imp):
                missing.append(imp)

        return missing

    def get_dependency_summary(self) -> str:
        """Get human-readable dependency summary"""
        venv = self.get_venv_info()
        reqs = self.parse_requirements_file("requirements.txt")
        missing = self.find_missing_dependencies()

        lines = [
            "📦 Dependency Summary",
            f"   Virtual Environment: {self.venv_path}",
        ]

        if venv:
            lines.extend([
                f"   Active: {'✓ YES' if venv.is_active else '✗ NO'}",
                f"   Installed Packages: {venv.total_packages}",
                f"   Outdated: {venv.outdated_packages}",
            ])

        lines.extend([
            f"\n   Requirements File: {reqs.path}",
            f"   Dependencies: {reqs.total}",
            f"   Installed: {reqs.installed}/{reqs.total}",
        ])

        if missing:
            lines.append(f"\n   ⚠️ Missing Dependencies: {len(missing)}")
            for dep in missing[:5]:
                lines.append(f"     • {dep}")
            if len(missing) > 5:
                lines.append(f"     ... and {len(missing) - 5} more")

        return "\n".join(lines)


# Singleton
dependency_manager = DependencyManager()
