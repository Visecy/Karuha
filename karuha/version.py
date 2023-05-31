from pkg_resources import get_distribution

__version__ = APP_VERSION = "0.1.0b0"
LIB_VERSION = get_distribution("tinode_grpc").version
