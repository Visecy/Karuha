from argparse import ArgumentParser
from pathlib import Path
import platform

from . import load_config, run
from .version import APP_VERSION, LIB_VERSION


useage = f"""
Karuha Runner v{APP_VERSION}

A easy way to run chatbots from a configuration file
""".strip()

version_info = ' '.join((
    f"%(prog)s v{APP_VERSION}",
    f"({platform.system()}/{platform.release()});",
    f"gRPC-python/{LIB_VERSION}"
))

parser = ArgumentParser("Karuha", usage=useage)
parser.add_argument("config", type=Path, nargs='?', default="config.json", help="path of the Karuha config")
parser.add_argument("--auto-create", action="store_true", help="auto create config")
parser.add_argument("--encoding", default="utf-8", help="config encoding")
parser.add_argument("-v", "--version", action="version", version=version_info)

if __name__ == "__main__":
    namespace = parser.parse_args()
    load_config(
        namespace.config,
        encoding=namespace.encoding,
        auto_create=namespace.auto_create
    )
    run()
