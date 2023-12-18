from typing import TYPE_CHECKING

from attr import frozen

from pybt2.runtime.types import Key

if TYPE_CHECKING:
    from .fibre import FibreNode


@frozen
class ChildAlreadyExistsError(Exception):
    key: Key
    existing_child: "FibreNode"
    new_child: "FibreNode"
