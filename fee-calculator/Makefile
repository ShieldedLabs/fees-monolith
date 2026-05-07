PYTHON ?= python3

.PHONY: test lint lint-html lint-css lint-py docker-build docker-run

test: lint

lint: lint-html lint-css lint-py

lint-html:
	npx --yes htmlhint index.html

lint-css:
	npx --yes stylelint style.css

lint-py:
	ruff check proxy.py

docker-build:
	docker build -t fee-calculator .

docker-run:
	docker run --rm -p 8081:8080 \
	  -e ZEBRA_HOST=host.docker.internal \
	  -e ZEBRA_PORT=8232 \
	  fee-calculator
