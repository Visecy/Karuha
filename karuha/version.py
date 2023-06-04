from pkg_resources import get_distribution

APP_VERSION = __version__ = "0.1.0b0"
LIB_VERSION = get_distribution("tinode_grpc").version
