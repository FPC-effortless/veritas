.PHONY: install test ci generate-example build clean

install:
	python -m pip install -e ".[test]"

test:
	python -m pytest tests/

ci: test
	python -m compileall -q src

build:
	python -m build

generate-example:
	python -m investigation_world.cli generate-world --seed 42 --output examples/world_001/world.json
	python -m investigation_world.cli render-evidence examples/world_001/world.json --output examples/world_001/evidence.json --seed 42

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	rm -rf build dist .coverage htmlcov
	find . -name .DS_Store -delete
