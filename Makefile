.PHONY: test generate-example clean install
install:
	python -m pip install -e ".[test]"
test:
	pytest tests/
generate-example:
	python -m investigation_world.cli generate-world --seed 42 --output examples/world_001/world.json
	python -m investigation_world.cli render-evidence --world examples/world_001/world.json --output examples/world_001/evidence.json
clean:
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type d -name .pytest_cache -exec rm -r {} +
	find . -name .DS_Store -delete
"}},{
