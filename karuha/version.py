from importlib.metadata import distribution

APP_VERSION = __version__ = "0.3.0a2"
LIB_VERSION = distribution("tinode_grpc").version
