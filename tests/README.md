# AnimeManager Testing Framework

This comprehensive testing framework provides multiple layers of testing for the AnimeManager application, including unit tests, integration tests, performance benchmarks, security testing, and end-to-end workflow validation.

## Test Structure

```
tests/
├── unit/                    # Unit tests for individual components
│   ├── db_managers/        # Database manager tests
│   ├── animeAPI/          # API client tests
│   ├── file_managers/      # File manager tests
│   └── ...
├── integration/            # Cross-component integration tests
├── performance/            # Performance benchmarking
├── gui/                    # GUI testing framework
├── security/               # Security regression tests
├── e2e/                    # End-to-end workflow tests
├── fixtures/               # Test data and fixtures
├── conftest.py            # Pytest configuration
├── test_config.py         # Test configuration and utilities
├── test_documentation.py  # Documentation testing
├── test_e2e_workflows.py  # E2E workflow tests
└── security_test.py       # Security regression tests
```

## Running Tests

### Basic Test Execution

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=. --cov-report=html

# Run specific test categories
python -m pytest -m "unit"          # Unit tests only
python -m pytest -m "integration"   # Integration tests only
python -m pytest -m "performance"   # Performance tests only
python -m pytest -m "security"      # Security tests only

# Run tests in parallel
python -m pytest -n auto

# Run with detailed output
python -m pytest -v -s
```

### Test Categories

- **unit**: Fast unit tests for individual functions/classes
- **integration**: Tests that verify component interactions
- **performance**: Benchmarking and performance regression tests
- **security**: Security vulnerability and regression tests
- **gui**: GUI component and accessibility tests
- **memory**: Memory usage and leak detection tests
- **load**: Load testing and concurrency tests
- **slow**: Tests that take longer to execute (excluded by default)

## Testing Frameworks

### 1. Unit Testing
Standard pytest-based unit tests with comprehensive mocking.

```python
def test_anime_search():
    mock_api = Mock()
    mock_api.search.return_value = [{"id": 1, "title": "Test"}]

    result = search_anime("test", api=mock_api)
    assert len(result) == 1
    assert result[0]["title"] == "Test"
```

### 2. GUI Testing Framework
Automated screenshot comparison and accessibility testing.

```python
class TestGUIComponents(BaseGUITest):
    def test_button_accessibility(self):
        button = tk.Button(self.root, text="Test Button")
        button.pack()

        # Test accessibility
        self.assert_accessible(button)

        # Test visual regression
        self.assert_screenshot_match(button, "test_button")
```

### 3. Performance Testing
Automated benchmarking with statistical analysis.

```python
@benchmark(iterations=100, warmup=10)
def test_database_query_performance(self):
    # Performance test implementation
    pass

def test_load_performance(self):
    def operation():
        time.sleep(0.01)  # Simulate work

    result = self.load_tester.run_concurrent_operations(operation, 50)
    assert result['operations_per_second'] > 50
```

### 4. Security Testing
Comprehensive security regression testing.

```python
def test_sql_injection_prevention(self):
    dangerous_inputs = ["'; DROP TABLE users; --", "' OR '1'='1"]

    for payload in dangerous_inputs:
        with self.assertRaises(Exception):
            vulnerable_function(payload)
```

### 5. End-to-End Testing
Complete workflow validation.

```python
@pytest.mark.asyncio
async def test_anime_search_download_workflow(self):
    result = await self.workflow_tester.simulate_anime_search_workflow()

    assert len(result['search_results']) > 0
    assert result['download_success'] is True
```

## Test Configuration

### pytest.ini Settings

```ini
[tool:pytest]
addopts = -v --cov=. --cov-report=html --cov-report=xml --cov-fail-under=85
markers =
    slow: marks tests as slow
    integration: marks tests as integration tests
    performance: marks tests as performance tests
    security: marks tests as security tests
```

### Test Fixtures

Common fixtures available in all tests:

```python
def test_with_mocks(mock_database, mock_api_client, sample_anime_data):
    # Test implementation using fixtures
    pass
```

## Code Quality Gates

### Automated Quality Checks

The CI/CD pipeline includes:

- **Flake8**: Code style and error checking
- **MyPy**: Static type checking
- **Bandit**: Security vulnerability scanning
- **Coverage**: Minimum 85% code coverage requirement

### Running Quality Checks Locally

```bash
# Code style
flake8 . --max-line-length=127

# Type checking
mypy . --ignore-missing-imports

# Security scanning
bandit -r . -f json

# Coverage
pytest --cov=. --cov-report=html --cov-fail-under=85
```

## Performance Benchmarking

### Running Benchmarks

```bash
# Run performance tests
pytest -m "performance" --benchmark-only

# Save benchmark results
pytest --benchmark-only --benchmark-save=benchmarks

# Compare benchmarks
pytest --benchmark-only --benchmark-compare=benchmarks
```

### Performance Thresholds

- Response time: < 1000ms for API calls
- Memory usage: < 500MB peak
- CPU usage: < 80% during normal operation
- Concurrent operations: Support 50+ simultaneous users

## Security Testing

### Automated Security Scans

```bash
# Run security tests
pytest -m "security"

# Security scanning tools
bandit -r . -f json -o bandit-report.json
safety check --json > safety-report.json
semgrep --config auto --json > semgrep-report.json .
```

### Security Test Categories

- SQL injection prevention
- XSS attack prevention
- Input validation and sanitization
- Authentication bypass prevention
- File upload security
- Session management security

## GUI Testing

### Screenshot Comparison

```python
def test_ui_component_visual(self):
    button = tk.Button(self.root, text="Test")
    button.pack()

    # Creates baseline on first run, compares on subsequent runs
    self.assert_screenshot_match(button, "test_button")
```

### Accessibility Testing

```python
def test_ui_accessibility(self):
    widget = tk.Label(self.root, text="Accessible Label")

    # Check accessibility compliance
    issues = self.accessibility_tester.check_widget_accessibility(widget)
    self.assertEqual(len(issues), 0)
```

## Documentation Testing

### Doctest Integration

```python
def test_documentation_examples(self):
    """Test that documentation examples execute correctly."""
    # Runs all doctests in Python files
    results = self.doc_tester.run_doctests_on_project()

    for result in results:
        assert result['failed'] == 0, f"Doctest failed in {result['file']}"
```

### README Validation

```python
def test_readme_examples(self):
    """Test code examples in README.md."""
    result = self.doc_tester.test_readme_examples()

    assert result['passed'] / result['total_blocks'] >= 0.8
```

## CI/CD Integration

### GitHub Actions Workflow

The `.github/workflows/ci.yml` provides:

- Multi-platform testing (Windows, macOS, Linux)
- Multi-Python version support (3.8-3.11)
- Automated security scanning
- Code quality gates
- Performance regression detection
- Automated reporting and notifications

### Running CI Locally

```bash
# Install CI dependencies
pip install -r requirements.txt

# Run full CI suite
python -m pytest --cov=. --cov-report=html --maxfail=5

# Run security scans
bandit -r . && safety check && semgrep --config auto .
```

## Test Data Management

### Fixtures and Test Data

Test data is managed through:

- `tests/fixtures/`: Static test data files
- `tests/conftest.py`: Pytest fixtures
- `tests/test_config.py`: Test configuration and utilities

### Creating Test Data

```python
@pytest.fixture
def sample_anime_data():
    return {
        "id": 1,
        "title": "Test Anime",
        "episodes": 12,
        "status": "completed"
    }
```

## Debugging Tests

### Common Debugging Techniques

```bash
# Run single test with debugging
pytest tests/test_specific.py::TestClass::test_method -v -s

# Run with PDB on failure
pytest --pdb

# Run with detailed tracebacks
pytest --tb=long

# Run slow tests only
pytest -m "slow" -v
```

### Test Isolation

Each test runs in isolation with:

- Fresh database instances
- Clean temporary directories
- Mocked external dependencies
- Proper cleanup after execution

## Contributing to Tests

### Test Development Guidelines

1. **Use descriptive test names**: `test_user_registration_with_valid_data`
2. **Follow AAA pattern**: Arrange, Act, Assert
3. **Use appropriate fixtures**: Leverage existing test fixtures
4. **Mock external dependencies**: Don't rely on real APIs/databases
5. **Test edge cases**: Include error conditions and boundary values
6. **Add performance tests**: For critical code paths
7. **Include security tests**: For user input handling

### Adding New Test Categories

```python
@pytest.mark.new_category
def test_new_functionality(self):
    # Test implementation
    pass
```

## Performance Optimization

### Identifying Performance Issues

```python
# Profile test execution
pytest --profile

# Memory profiling
pytest --memory

# Benchmark specific functions
@benchmark(iterations=1000)
def test_critical_function(self):
    # Implementation
    pass
```

### Performance Baselines

The framework maintains performance baselines to detect regressions:

- Response time baselines
- Memory usage baselines
- CPU usage baselines
- Throughput baselines

## Security Considerations

### Test Security Best Practices

- Never commit real credentials or secrets
- Use mock data for sensitive operations
- Test security controls thoroughly
- Include penetration testing scenarios
- Validate input sanitization
- Test authentication and authorization

### Security Test Examples

```python
def test_password_hashing_security(self):
    """Test password hashing meets security standards."""
    hash_func = lambda pwd: hashlib.sha256(pwd.encode()).hexdigest()

    self.auth_tester.test_password_hashing(hash_func)

def test_input_validation(self):
    """Test input validation prevents attacks."""
    dangerous_inputs = ["<script>alert('XSS')</script>", "'; DROP TABLE;"]

    for input_str in dangerous_inputs:
        with self.assertRaises(ValueError):
            process_user_input(input_str)
```

This testing framework provides comprehensive coverage of all aspects of the AnimeManager application, ensuring reliability, security, and performance across all components and user workflows.