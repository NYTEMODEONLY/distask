from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logger = logging.getLogger("distask.validate")


class ValidationResult:
    def __init__(self, name: str, passed: bool, message: str = "", warnings: List[str] = None):
        self.name = name
        self.passed = passed
        self.message = message
        self.warnings = warnings or []

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"{self.name}: {status} - {self.message}"


def check_command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    try:
        subprocess.run(
            ["which", cmd] if sys.platform != "win32" else ["where", cmd],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def validate_black() -> ValidationResult:
    """Validate code formatting with black."""
    if not check_command_exists("black"):
        return ValidationResult("black", True, "black not installed (skipped)", ["black not found"])
    
    try:
        result = subprocess.run(
            ["black", "--check", "--diff", str(ROOT_DIR)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return ValidationResult("black", True, "Code formatting is correct")
        else:
            diff = result.stdout[:500] if result.stdout else "See output above"
            return ValidationResult("black", False, f"Formatting issues found:\n{diff}")
    except subprocess.TimeoutExpired:
        return ValidationResult("black", False, "black check timed out")
    except Exception as e:
        return ValidationResult("black", False, f"Error running black: {e}")


def validate_flake8() -> ValidationResult:
    """Validate code style with flake8."""
    if not check_command_exists("flake8"):
        return ValidationResult("flake8", True, "flake8 not installed (skipped)", ["flake8 not found"])
    
    try:
        result = subprocess.run(
            ["flake8", str(ROOT_DIR), "--exclude=.venv,venv,__pycache__,.git"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return ValidationResult("flake8", True, "Code style is correct")
        else:
            issues = result.stdout[:500] if result.stdout else "See output above"
            return ValidationResult("flake8", False, f"Style issues found:\n{issues}")
    except subprocess.TimeoutExpired:
        return ValidationResult("flake8", False, "flake8 check timed out")
    except Exception as e:
        return ValidationResult("flake8", False, f"Error running flake8: {e}")


def validate_mypy() -> ValidationResult:
    """Validate type hints with mypy (non-blocking)."""
    if not check_command_exists("mypy"):
        return ValidationResult("mypy", True, "mypy not installed (skipped)", ["mypy not found"])
    
    try:
        result = subprocess.run(
            ["mypy", str(ROOT_DIR), "--ignore-missing-imports", "--no-strict-optional"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return ValidationResult("mypy", True, "Type checking passed")
        else:
            issues = result.stdout[:1000] if result.stdout else "See output above"
            return ValidationResult("mypy", True, f"Type issues (non-blocking):\n{issues}", ["Type checking warnings"])
    except subprocess.TimeoutExpired:
        return ValidationResult("mypy", True, "mypy check timed out (non-blocking)", ["Type check timeout"])
    except Exception as e:
        return ValidationResult("mypy", True, f"Error running mypy (non-blocking): {e}", ["Type check error"])


def validate_pytest() -> ValidationResult:
    """Run tests with pytest (graceful if no tests exist)."""
    if not check_command_exists("pytest"):
        return ValidationResult("pytest", True, "pytest not installed (skipped)", ["pytest not found"])
    
    tests_dir = ROOT_DIR / "tests"
    if not tests_dir.exists() or not any(tests_dir.glob("test_*.py")):
        return ValidationResult("pytest", True, "No tests found (skipped)", ["No test files detected"])
    
    try:
        result = subprocess.run(
            ["pytest", str(tests_dir), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return ValidationResult("pytest", True, "All tests passed")
        else:
            output = result.stdout[:1000] if result.stdout else result.stderr[:1000] if result.stderr else "See output above"
            return ValidationResult("pytest", False, f"Tests failed:\n{output}")
    except subprocess.TimeoutExpired:
        return ValidationResult("pytest", False, "pytest run timed out")
    except Exception as e:
        return ValidationResult("pytest", False, f"Error running pytest: {e}")


def validate_git_state() -> ValidationResult:
    """Validate git working tree is clean and up to date."""
    try:
        # Check if in git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            cwd=ROOT_DIR,
            check=False,
        )
        if result.returncode != 0:
            return ValidationResult("git_state", True, "Not a git repository (skipped)", ["No git repo"])
        
        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            check=False,
        )
        if result.stdout.strip():
            return ValidationResult("git_state", False, f"Uncommitted changes detected:\n{result.stdout[:500]}")
        
        # Check if up to date with origin (non-blocking warning)
        result = subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=10,
            check=False,
        )
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip().isdigit():
            behind = int(result.stdout.strip())
            if behind > 0:
                return ValidationResult(
                    "git_state",
                    True,
                    f"Working tree clean but {behind} commits behind origin/main",
                    [f"{behind} commits behind origin"],
                )
        
        return ValidationResult("git_state", True, "Working tree is clean")
    except subprocess.TimeoutExpired:
        return ValidationResult("git_state", True, "Git check timed out (non-blocking)", ["Git check timeout"])
    except Exception as e:
        return ValidationResult("git_state", True, f"Error checking git state (non-blocking): {e}", ["Git check error"])


def validate_feature_queue_consistency() -> ValidationResult:
    """Validate feature queue JSON and MD are consistent."""
    json_path = ROOT_DIR / "automation" / "feature_queue.json"
    md_path = ROOT_DIR / "automation" / "feature_queue.md"
    
    if not json_path.exists():
        return ValidationResult("queue_consistency", True, "feature_queue.json not found (skipped)")
    
    try:
        with open(json_path, "r") as f:
            queue_data = json.load(f)
        
        items = queue_data.get("items", [])
        json_ids = {item["id"] for item in items if "id" in item}
        
        if md_path.exists():
            md_content = md_path.read_text()
            # Extract IDs from markdown table (basic check)
            import re
            md_ids = set(re.findall(r"\|\s*(\d+)\s*\|", md_content))
            md_ids = {int(id) for id in md_ids if id.isdigit()}
            
            if json_ids != md_ids:
                missing_in_md = json_ids - md_ids
                missing_in_json = md_ids - json_ids
                msg = f"Queue mismatch: JSON has {len(json_ids)} items, MD has {len(md_ids)} items"
                if missing_in_md:
                    msg += f"\nMissing in MD: {sorted(missing_in_md)[:5]}"
                if missing_in_json:
                    msg += f"\nMissing in JSON: {sorted(missing_in_json)[:5]}"
                return ValidationResult("queue_consistency", False, msg)
        
        return ValidationResult("queue_consistency", True, f"Queue consistency verified ({len(json_ids)} items)")
    except Exception as e:
        return ValidationResult("queue_consistency", False, f"Error validating queue: {e}")


def validate_schema_compatibility(db_url: Optional[str] = None) -> ValidationResult:
    """Validate database schema compatibility (basic check)."""
    if not db_url:
        return ValidationResult("schema", True, "Database URL not provided (skipped)", ["No DB URL"])
    
    try:
        # Import here to avoid circular dependencies
        from utils import Database
        
        async def check_schema():
            db = Database(db_url)
            try:
                await db.init()
                # Try a simple query to verify schema exists
                await db._execute("SELECT 1 FROM guilds LIMIT 1", fetchone=True)
                return True
            except Exception as e:
                logger.error("Schema check failed: %s", e)
                return False
            finally:
                await db.close()
        
        import asyncio
        is_valid = asyncio.run(check_schema())
        if is_valid:
            return ValidationResult("schema", True, "Database schema is compatible")
        else:
            return ValidationResult("schema", False, "Database schema check failed")
    except ImportError:
        return ValidationResult("schema", True, "Database module not available (skipped)", ["DB import failed"])
    except Exception as e:
        return ValidationResult("schema", False, f"Error checking schema: {e}")


def validate_duplicate_fr_markers() -> ValidationResult:
    """Check for duplicate FR markers in recent commits (if git available)."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-20", "--all"],
            capture_output=True,
            text=True,
            cwd=ROOT_DIR,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return ValidationResult("fr_markers", True, "Git not available (skipped)")
        
        import re
        commits = result.stdout.splitlines()
        fr_pattern = re.compile(r"FR-(\d+)", re.IGNORECASE)
        seen_markers: Dict[int, List[str]] = {}
        
        for commit in commits:
            matches = fr_pattern.findall(commit)
            for fr_id in matches:
                fid = int(fr_id)
                if fid not in seen_markers:
                    seen_markers[fid] = []
                seen_markers[fid].append(commit[:50])
        
        duplicates = {fid: commits for fid, commits in seen_markers.items() if len(commits) > 1}
        if duplicates:
            msg = f"Found {len(duplicates)} FR markers appearing in multiple commits"
            for fid, commit_list in list(duplicates.items())[:3]:
                msg += f"\nFR-{fid} appears in {len(commit_list)} commits"
            return ValidationResult("fr_markers", True, msg, ["Duplicate FR markers detected"])
        
        return ValidationResult("fr_markers", True, "No duplicate FR markers detected")
    except Exception as e:
        return ValidationResult("fr_markers", True, f"Error checking FR markers (non-blocking): {e}", ["FR check error"])


def run_all_validations(
    db_url: Optional[str] = None,
    skip_tests: bool = False,
    skip_type_check: bool = False,
) -> Tuple[List[ValidationResult], bool]:
    """
    Run all validation checks.
    
    Returns:
        Tuple of (results list, overall success)
    """
    results: List[ValidationResult] = []
    
    # Critical validations (blocking)
    logger.info("Running critical validations...")
    results.append(validate_git_state())
    results.append(validate_feature_queue_consistency())
    
    # Code quality (blocking)
    logger.info("Running code quality checks...")
    results.append(validate_black())
    results.append(validate_flake8())
    
    # Type checking (non-blocking warnings)
    if not skip_type_check:
        logger.info("Running type checks...")
        results.append(validate_mypy())
    
    # Tests (blocking if tests exist)
    if not skip_tests:
        logger.info("Running tests...")
        results.append(validate_pytest())
    
    # Database schema (blocking if DB URL provided)
    if db_url:
        logger.info("Checking database schema...")
        results.append(validate_schema_compatibility(db_url))
    
    # FR marker check (non-blocking)
    logger.info("Checking FR markers...")
    results.append(validate_duplicate_fr_markers())
    
    # Determine overall success (fail if any critical check failed)
    critical_checks = ["black", "flake8", "pytest", "git_state", "queue_consistency", "schema"]
    failed_critical = [
        r for r in results
        if r.name in critical_checks and not r.passed
    ]
    
    overall_success = len(failed_critical) == 0
    
    return results, overall_success


def print_validation_summary(results: List[ValidationResult], overall_success: bool) -> None:
    """Print a formatted summary of validation results."""
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    for result in results:
        status = "✓" if result.passed else "✗"
        print(f"{status} {result.name}: {result.message}")
        if result.warnings:
            for warning in result.warnings:
                print(f"  ⚠ Warning: {warning}")
    
    print("=" * 70)
    if overall_success:
        print("✓ All critical validations passed")
    else:
        print("✗ Some critical validations failed")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate DisTask codebase")
    parser.add_argument("--db-url", help="Database URL for schema validation")
    parser.add_argument("--skip-tests", action="store_true", help="Skip test execution")
    parser.add_argument("--skip-type-check", action="store_true", help="Skip type checking")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    
    results, success = run_all_validations(
        db_url=args.db_url,
        skip_tests=args.skip_tests,
        skip_type_check=args.skip_type_check,
    )
    
    if not args.quiet:
        print_validation_summary(results, success)
    
    sys.exit(0 if success else 1)

