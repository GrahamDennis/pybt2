from typing import Generic, Iterator, Optional, Sequence, Type, TypeVar, cast

from attr import frozen
from typing_extensions import Self

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.types import AbstractContextKey, CaptureKey, FibreNodeFunction, FibreNodeState

T = TypeVar("T")

DEFAULT_CAPTURE_CHILD_KEY = "__CaptureProvider.Child"
DEFAULT_CAPTURE_CONSUMER_KEY = "__CaptureProvider.Consumer"


@frozen(weakref_slot=False)
class CaptureProvider(FibreNodeFunction[Sequence[T], None, None], Generic[T]):
    capture_key: CaptureKey[T]
    child: FibreNodeFunction

    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[Self, Sequence[T], None, None],
        previous_state: Optional[FibreNodeState[Self, Sequence[T], None]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, Sequence[T], None]:
        context_map: dict[AbstractContextKey, FibreNode] = {}
        _child_fibre_node = FibreNode.create(
            key=self.child.key if self.child.key is not None else DEFAULT_CAPTURE_CHILD_KEY,
            parent=fibre_node,
            props_type=type(self.child),
            fibre_node_function_type=cast(Type[FibreNodeFunction], type(self.child)),
            contexts=fibre_node.contexts.new_child(context_map),
        )
        raise NotImplementedError()
