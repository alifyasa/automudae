.PHONY: format lint check all up down

up:
	docker compose up --build --force-recreate --detach --remove-orphans

down:
	docker compose down

format:
	find automudae/ -name '*.py' -exec autoflake {} \
	    --in-place \
	    --remove-all-unused-imports \
	    --remove-unused-variables \
	    --remove-duplicate-keys \
	    --verbose \
	    \;
	isort automudae/ --profile=black
	black automudae/

lint: format
	mypy automudae/
	pylint automudae/

check: lint
	pyflakes automudae/

all: format lint check
