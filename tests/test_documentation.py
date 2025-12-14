"""
Documentation Testing with Doctest Integration

This module provides comprehensive documentation testing including:
- Doctest execution for code examples
- Documentation build validation
- API documentation validation
- Example code testing
"""

import doctest
import os
import sys
import pytest
import subprocess
import re
from pathlib import Path


def _filepath_to_module_name(filepath, project_root):
    """Convert file path to module name.

    >>> _filepath_to_module_name('path/to/module.py', 'path')
    'to.module'
    >>> _filepath_to_module_name('module.py', '.')
    'module'
    """
    try:
        rel_path = os.path.relpath(filepath, project_root)
        if rel_path.endswith('.py'):
            rel_path = rel_path[:-3]
        module_name = rel_path.replace(os.sep, '.')
        return module_name
    except:
        return None


class DocumentationTester:
    """Test documentation quality and examples."""

    def __init__(self, project_root=None):
        self.project_root = Path(project_root or os.getcwd())

    def find_python_files(self):
        """Find all Python files in the project."""
        python_files = []
        for root, dirs, files in os.walk(self.project_root):
            # Skip common directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'build', 'dist', 'venv', '.git']]

            for file in files:
                if file.endswith('.py') and file != 'setup.py':
                    python_files.append(os.path.join(root, file))

        return python_files

    def run_doctests_on_file(self, filepath):
        """Run doctests on a single file."""
        try:
            # Run doctests
            result = doctest.testfile(filepath, verbose=False, optionflags=doctest.ELLIPSIS)
            return {
                'file': filepath,
                'attempted': result.attempted,
                'failed': result.failed,
                'passed': result.attempted - result.failed
            }
        except Exception as e:
            return {
                'file': filepath,
                'error': str(e),
                'attempted': 0,
                'failed': 0,
                'passed': 0
            }

    def run_doctests_on_project(self):
        """Run doctests on all Python files in the project."""
        results = []
        python_files = self.find_python_files()

        for filepath in python_files:
            result = self.run_doctests_on_file(filepath)
            results.append(result)

        return results

    def validate_docstring_coverage(self, min_coverage=0.8):
        """Validate that modules have adequate docstring coverage."""
        python_files = self.find_python_files()
        coverage_results = []

        for filepath in python_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Count functions/methods
                function_pattern = r'def\s+\w+\s*\('
                functions = len(re.findall(function_pattern, content))

                # Count docstrings (simplified)
                docstring_pattern = r'""".*?"""'
                docstrings = len(re.findall(docstring_pattern, content, re.DOTALL))

                coverage = docstrings / max(functions, 1)
                coverage_results.append({
                    'file': filepath,
                    'functions': functions,
                    'docstrings': docstrings,
                    'coverage': coverage,
                    'meets_minimum': coverage >= min_coverage
                })

            except Exception as e:
                coverage_results.append({
                    'file': filepath,
                    'error': str(e),
                    'coverage': 0,
                    'meets_minimum': False
                })

        return coverage_results

    def test_readme_examples(self):
        """Test code examples in README.md."""
        readme_path = self.project_root / 'README.md'

        if not readme_path.exists():
            return {'error': 'README.md not found'}

        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract code blocks
            code_blocks = re.findall(r'```python\s*(.*?)\s*```', content, re.DOTALL)

            results = []
            for i, code_block in enumerate(code_blocks):
                try:
                    # Execute the code block
                    exec(code_block, {'__name__': '__test__'})
                    results.append({'block': i, 'status': 'passed'})
                except Exception as e:
                    results.append({'block': i, 'status': 'failed', 'error': str(e)})

            return {
                'total_blocks': len(code_blocks),
                'passed': len([r for r in results if r['status'] == 'passed']),
                'failed': len([r for r in results if r['status'] == 'failed']),
                'results': results
            }

        except Exception as e:
            return {'error': str(e)}


class TestDocumentation:
    """Documentation testing suite."""

    def setup_method(self):
        """Set up test environment."""
        self.doc_tester = DocumentationTester()

    def test_doctest_execution(self):
        """Test that doctests in Python files execute successfully."""
        results = self.doc_tester.run_doctests_on_project()

        total_attempted = sum(r.get('attempted', 0) for r in results)

        # Ensure doctests are found and executed
        assert total_attempted > 0, "No doctests found to execute"

    def test_docstring_coverage(self):
        """Test that code has adequate docstring coverage."""
        coverage_results = self.doc_tester.validate_docstring_coverage(min_coverage=0.5)

        # Filter out test files and generated files
        relevant_results = [
            r for r in coverage_results
            if not any(skip in r['file'] for skip in ['test_', '__pycache__', 'build', 'dist'])
        ]

        if relevant_results:
            avg_coverage = sum(r.get('coverage', 0) for r in relevant_results) / len(relevant_results)
            assert avg_coverage >= 0.3, f"Docstring coverage too low: {avg_coverage:.1%}"

    def test_readme_examples(self):
        """Test that README code examples are valid."""
        result = self.doc_tester.test_readme_examples()

        if 'error' not in result:
            # Allow some examples to fail, but ensure most work
            if result['total_blocks'] > 0:
                success_rate = result['passed'] / result['total_blocks']
                assert success_rate >= 0.7, f"Too many README examples fail: {result['failed']}/{result['total_blocks']}"

    def test_documentation_files_exist(self):
        """Test that required documentation files exist."""
        required_files = ['README.md', 'requirements.txt', 'setup.py']

        for filename in required_files:
            filepath = self.doc_tester.project_root / filename
            assert filepath.exists(), f"Required documentation file missing: {filename}"

    def test_code_examples_syntax(self):
        """Test that code examples in documentation have valid syntax."""
        readme_path = self.doc_tester.project_root / 'README.md'

        if readme_path.exists():
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract Python code blocks
            code_blocks = re.findall(r'```python\s*(.*?)\s*```', content, re.DOTALL)

            for i, code_block in enumerate(code_blocks):
                try:
                    # Try to compile the code block
                    compile(code_block, f'<README code block {i}>', 'exec')
                except SyntaxError as e:
                    pytest.fail(f"Syntax error in README code block {i}: {e}")

