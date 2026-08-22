SHELL := /bin/bash

LLAMA_ROOT ?= $(CURDIR)/src/llama-upstream
BUILD_DIR ?= $(LLAMA_ROOT)/build

.PHONY: bootstrap build test check docs clean

bootstrap:
	SLIM_ARC_LLAMA_ROOT="$(LLAMA_ROOT)" bash scripts/bootstrap-dev.sh

build:
	@test -f "$(BUILD_DIR)/CMakeCache.txt" || { echo "Run 'make bootstrap' first." >&2; exit 1; }
	cmake --build "$(BUILD_DIR)" --config Release -j

test:
	bash tests/run-cpp-unit.sh all
	uv run pytest -q

check:
	bash -n scripts/bootstrap-dev.sh scripts/macos/run-native-demo.sh tests/run-cpp-unit.sh
	PYTHONPYCACHEPREFIX="$(CURDIR)/.cache/python" python3 -m compileall -q scripts tests
	uv run ruff check --select E9,F63,F7,F82 scripts tests reports/Competition_Report_Finals
	python3 scripts/check-public-tree.py
	python3 scripts/check-markdown-links.py

docs:
	python3 reports/Competition_Report_Finals/build_finals_report.py

clean:
	@if [[ -d "$(BUILD_DIR)" ]]; then cmake --build "$(BUILD_DIR)" --target clean; fi
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf -- {} +
