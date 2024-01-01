.PHONY: run install develop build_dist test coverage clean

MODULE := karuha
PIP_MODULE := KaruhaBot

all: clean lint build_dist
refresh: clean develop test lint

run:
	python -m ${MODULE}

build:
	python setup.py build

build_dist:
	python setup.py sdist bdist_wheel

install:
	pip install .

develop:
	pip install -e .

lint:
	flake8 ${MODULE}/ tests/ --exclude __init__.py --count --max-line-length=127 --extend-ignore=W293,E402

test:
	python -m unittest

coverage:
	coverage run --source ${MODULE} --parallel-mode -m unittest
	coverage combine
	coverage html -i

uninstall:
	pip uninstall ${PIP_MODULE} -y || true

clean:
	rm -rf build
	rm -rf dist
	rm -rf ${PIP_MODULE}.egg-info
