from collections.abc import Callable
from typing import assert_type

from arboresce import NAME, __version__, name, print_name

assert_type(NAME, str)
assert_type(__version__, str)
assert_type(name(), str)
printer: Callable[[], None] = print_name


def consume() -> str:
    print_name()
    return name()
