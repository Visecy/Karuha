from grpc import RpcError


class KaruhaException(Exception):
    """base exception for all errors in Karuha module"""
    __slots__ = []


class KaruhaConnectError(KaruhaException, RpcError):
    """grpc connection error"""
