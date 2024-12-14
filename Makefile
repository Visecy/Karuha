.PHONY: run install install_all refresh uninstall develop build_dist test coverage clean

MODULE := karuha
PIP_MODULE := KaruhaBot

all: clean test lint build_dist
refresh: clean develop test lint

run:
	python -m ${MODULE}

build:
	python setup.py build

build_dist: test
	python -m build

install:
	pip install .

install_all:
	pip install .[all]

develop:
	pip install -e .[dev]

lint:
	flake8 ${MODULE}/ tests/ --exclude __init__.py --count --max-line-length=127 --extend-ignore=W293,E402

test:
	pytest

test_online:
	pytest tests/online/

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
