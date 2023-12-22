from typing import TYPE_CHECKING, Generic

from attr import frozen

from pybt2.runtime.types import Key, PropsT

if TYPE_CHECKING:
    from .fibre import FibreNode


@frozen
class ChildAlreadyExistsError(Exception):
    key: Key
    existing_child: "FibreNode"


@frozen
class PropsTypeConflictError(Exception, Generic[PropsT]):
    props: PropsT
    expected_type: type
