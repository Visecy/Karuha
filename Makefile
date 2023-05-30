.PHONY: build build_cython install build_dist test docs clean

MODULE := karuha
PIP_MODULE := KaruhaBot

all: clean build lint build_dist
refresh: clean install lint

build_lexer: kola/lex.yy.c build

kola/lex.yy.c: kola/kolalexer.l
	flex kola/kolalexer.l

build_cython:
	USE_CYTHON=true python setup.py build_ext --inplace

build:
	python setup.py build_ext --inplace

run:
	python -m ${MODULE}

develop:
	python setup.py develop

build_dist:
	python setup.py sdist bdist_wheel

install: build_dist
	pip install dist/${PIP_MODULE}*.tar.gz

lint:
	flake8 ${MODULE}/ tests/ --exclude __init__.py --count --max-line-length=127 --extend-ignore=W293,E402

test: build
	python -m unittest

coverage:
	coverage run --source ${MODULE} --parallel-mode -m unittest
	coverage combine
	coverage html -i

uninstall:
	pip uninstall ${PIP_MODULE} -y || true

docs:
	cd docs/api && make html

clean:
	rm -rf build
	rm -rf dist
	rm -rf ${PIP_MODULE}.egg-info


