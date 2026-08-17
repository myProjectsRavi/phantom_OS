PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: install compile test lint format format-check typecheck coverage benchmark benchmark-smoke security public-safety build wheel-smoke verify clean smoke smoke-strict

install:
	$(PYTHON) -m pip install -e '.[dev]'

compile:
	$(PYTHON) -m compileall -q src tests scripts benchmarks

test:
	$(PYTHON) -m pytest -q

lint:
	PYTHONPATH=src $(PYTHON) -m ruff check src tests scripts benchmarks

format:
	$(PYTHON) -m ruff format src tests scripts benchmarks

format-check:
	PYTHONPATH=src $(PYTHON) -m ruff format --check src tests scripts benchmarks

typecheck:
	PYTHONPATH=src $(PYTHON) -m mypy --ignore-missing-imports src/phantom

coverage:
	PYTHONPATH=src $(PYTHON) -m pytest -q --cov=phantom --cov-report=term-missing --cov-report=xml:coverage.xml --cov-fail-under=95

benchmark:
	PYTHONPATH=src $(PYTHON) -m pytest benchmarks -q --benchmark-only --no-cov

benchmark-smoke:
	PYTHONPATH=src $(PYTHON) -m pytest benchmarks -q --benchmark-disable --no-cov

security:
	$(PYTHON) -m bandit -r src/phantom/ -ll -ii -x '*/tests/*'
	$(PYTHON) -m pip_audit --progress-spinner off

public-safety:
	$(PYTHON) scripts/check_public_snapshot.py

build:
	$(PYTHON) -m pip install --quiet build
	$(PYTHON) -m build

wheel-smoke: build
	rm -rf .verify-wheel-venv
	$(PYTHON) -m venv .verify-wheel-venv
	.verify-wheel-venv/bin/python -m pip install --quiet --upgrade pip
	.verify-wheel-venv/bin/pip install --quiet dist/*.whl
	.verify-wheel-venv/bin/phantom --help >/dev/null
	.verify-wheel-venv/bin/python -c 'from phantom.config import PhantomConfig; PhantomConfig()'
	rm -rf .verify-wheel-venv

# Zero-cost local equivalent of the core GitHub release gates for the current
# interpreter. Run this on each supported Python version (3.10-3.13) before release.
verify: compile lint format-check typecheck coverage benchmark-smoke security public-safety wheel-smoke

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__ htmlcov dist build *.egg-info coverage.xml .verify-wheel-venv

# Backward-compatible aliases now run the public snapshot hygiene check.
smoke: public-safety

smoke-strict: public-safety
