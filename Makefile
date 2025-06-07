.PHONY: format lint check all

format:
	echo "Running format..."
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
	echo "Running lint..."
	mypy automudae/
	pylint automudae/

check: lint
	echo "Running check..."
	pyflakes automudae/

all: format lint check
