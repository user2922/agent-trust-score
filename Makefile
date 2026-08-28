# Every target delegates to scripts/, so there is one implementation and it runs
# on machines without make (this project was built on one).
.PHONY: lint typecheck secrets test check-all

lint:
	uv run ruff check .

typecheck:
	uv run mypy agent_trust

secrets:
	bash scripts/check_secrets.sh

test:
	uv run pytest

check-all:
	bash scripts/check_all.sh
