"""
Copyright 2024 Ovizro

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
import platform
from argparse import ArgumentParser
from importlib import import_module
from pathlib import Path

from . import load_config, run
from .version import APP_VERSION, LIB_VERSION


description = """
A easy way to run chatbots from a configuration file
""".strip()

version_info = ' '.join((
    f"%(prog)s v{APP_VERSION}",
    f"({platform.system()}/{platform.release()});",
    f"gRPC-python/{LIB_VERSION}"
))

default_config = os.environ.get("KARUHA_CONFIG", "config.json")
default_modules = os.environ.get("KARUHA_MODULES", "").split(os.pathsep)

parser = ArgumentParser("Karuha", description=description)
parser.add_argument("config", type=Path, nargs='?', default=default_config, help="path of the Karuha config")
parser.add_argument("--auto-create", action="store_true", help="auto create config")
parser.add_argument("--encoding", default="utf-8", help="config encoding")
parser.add_argument("-m", "--module", type=str, action="append", help="module to load", default=default_modules)
parser.add_argument("-v", "--version", action="version", version=version_info)


if __name__ == "__main__":
    namespace = parser.parse_args()
    load_config(
        namespace.config,
        encoding=namespace.encoding,
        auto_create=namespace.auto_create
    )
    if namespace.module:
        for module in namespace.module:
            if not module:
                continue
            import_module(module)
    run()
