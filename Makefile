PYTHON ?= python3

.PHONY: test lint lint-html lint-css lint-py docker-build docker-run

test: lint-html lint-css lint-py
	$(PYTHON) -m unittest discover -s tests

lint: lint-html lint-css lint-py

lint-html:
	npx --yes htmlhint index.html proposal.html calculator.html zip-proposal.html

lint-css:
	npx --yes stylelint style.css

lint-py:
	ruff check .

docker-build:
	docker build -t fee-calculator .

docker-run:
	docker run --rm -p 8081:8080 \
    -e ZEBRA_HOST=host.docker.internal \
    -e ZEBRA_PORT=8234 \
    -v ~/.cache/zebra/.cookie:/root/.cache/zebra/.cookie:ro \
    fee-calculator
