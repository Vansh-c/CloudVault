# Contributing to CloudVault

Thank you for your interest in contributing to CloudVault! This document provides guidelines for contributing to the project.

## Code of Conduct

By participating in this project, you agree to use this tool responsibly and only for authorized security testing.

## How to Contribute

### Reporting Issues

- Check if the issue already exists
- Include Python version and OS information
- Provide clear reproduction steps
- Include relevant logs (sanitized of sensitive data)

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest`)
6. Format code with Black (`black cloudvault_discovery/`)
7. Run type checking (`mypy cloudvault_discovery/`)
8. Commit with clear messages
9. Push to your fork
10. Open a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/CloudVault.git
cd CloudVault

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .[dev,all]

# Run tests
pytest

# Format code
black cloudvault_discovery/

# Type checking
mypy cloudvault_discovery/
```

### Coding Standards

- Follow PEP 8
- Use type hints for all functions
- Write docstrings for public functions
- Keep functions focused and small
- Add unit tests for new features
- Maintain backwards compatibility

### Testing

- Write tests for all new functionality
- Ensure 80%+ code coverage
- Test edge cases and error conditions
- Mock external API calls

### Security Considerations

- Never commit credentials or sensitive data
- Sanitize all user inputs
- Rate limit external API calls
- Follow responsible disclosure practices
- Document security implications

### Documentation

- Update README for user-facing changes
- Add docstrings to new functions
- Update CHANGELOG.md
- Include examples for new features

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create git tag
4. Build and publish to PyPI

## Questions?

Feel free to open an issue for any questions about contributing!