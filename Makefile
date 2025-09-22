.PHONY: help install install-dev test lint format type-check clean build publish

help:
	@echo "Available commands:"
	@echo "  install      Install the package"
	@echo "  install-dev  Install with development dependencies"
	@echo "  test         Run tests"
	@echo "  lint         Run linting checks"
	@echo "  format       Format code with Black"
	@echo "  type-check   Run type checking with mypy"
	@echo "  clean        Clean build artifacts"
	@echo "  build        Build distribution packages"
	@echo "  publish      Publish to PyPI"

install:
	pip install -e .

install-dev:
	pip install -e .[dev,all]

test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ --cov=cloudvault_discovery --cov-report=html

lint:
	python -m flake8 cloudvault_discovery/
	python -m bandit -r cloudvault_discovery/

format:
	python -m black cloudvault_discovery/ tests/

type-check:
	python -m mypy cloudvault_discovery/

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache/ .coverage htmlcov/

build: clean
	python -m build

publish: build
	python -m twine upload dist/*

run:
	python -m cloudvault_discovery.cli

run-test:
	python -m cloudvault_discovery.cli -s test-domains.txt --verbose