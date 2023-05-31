.PHONY: build build_cython install build_dist test docs clean

MODULE := karuha
PIP_MODULE := KaruhaBot

all: clean build lint build_dist
refresh: clean install lint

run:
	python -m ${MODULE}

build_dist:
	python setup.py sdist bdist_wheel

install: build_dist
	pip install dist/${PIP_MODULE}*.tar.gz

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


