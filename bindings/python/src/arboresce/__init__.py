from .arboresce_ffi import name, print_name

NAME: str = name()
__version__: str = "0.0.0"

__all__ = ["NAME", "__version__", "name", "print_name"]
