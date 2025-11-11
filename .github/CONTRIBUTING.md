# Contributing to Enphase Battery Integration

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Code Quality

This project uses several tools to maintain code quality:

### Ruff (Linter & Formatter)

Ruff is an extremely fast Python linter and formatter that replaces multiple tools:

```bash
# Install Ruff
pip install ruff

# Check code
ruff check custom_components/

# Auto-fix issues
ruff check custom_components/ --fix

# Format code
ruff format custom_components/
```

Configuration is in `pyproject.toml`.

### Pre-commit Hooks (Optional)

For automatic code quality checks before commits:

```bash
# Install pre-commit
pip install pre-commit

# Install the hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### Type Checking with MyPy (Optional)

```bash
# Install MyPy
pip install mypy types-aiofiles

# Run type checking
mypy custom_components/enphase_battery --ignore-missing-imports
```

## GitHub Actions

All pull requests and commits to main are automatically checked with:

1. **Ruff linting** - Code style and common errors
2. **Ruff formatting** - Code formatting consistency
3. **Hassfest** - Home Assistant integration validation
4. **HACS validation** - HACS requirements check
5. **Manifest validation** - JSON syntax and structure
6. **Common issues check** - Debug statements, urgent TODOs

## Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run quality checks: `ruff check --fix && ruff format`
5. Commit your changes: `git commit -m "feat: add my feature"`
6. Push to your fork: `git push origin feature/my-feature`
7. Create a Pull Request

## Commit Message Convention

Use conventional commits format:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Example: `feat: add support for multiple batteries`

## Code Style Guidelines

- Follow PEP 8 conventions (enforced by Ruff)
- Maximum line length: 120 characters
- Use type hints for all function parameters and returns
- Write docstrings for public functions and classes
- Keep functions focused and under 50 lines when possible
- Use descriptive variable names

## Testing

Before submitting a PR:

1. Test with a real Enphase system if possible
2. Check logs for errors and warnings
3. Verify all switches and sensors work correctly
4. Test in both local and cloud modes if applicable

## Questions?

Open an issue for:
- Bug reports
- Feature requests
- Questions about the code
- Help with development setup

Thank you for contributing! 🚀
