from typing import Generic, Iterator, Mapping, Optional, Sequence, Type, TypeVar, cast

from attr import frozen
from typing_extensions import Self

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.types import AbstractContextKey, CaptureKey, FibreNodeFunction, FibreNodeState

T = TypeVar("T")

DEFAULT_CAPTURE_CHILD_KEY = "__CaptureProvider.Child"
CAPTURE_CONSUMER_KEY = "__CaptureProvider.Consumer"


@frozen(weakref_slot=False)
class AddCaptureEntry(Generic[T]):
    fibre_node: FibreNode
    value: T


@frozen(weakref_slot=False)
class RemoveCaptureEntry:
    fibre_node: FibreNode


CaptureEntryAction = AddCaptureEntry[T] | RemoveCaptureEntry


@frozen(weakref_slot=False)
class CaptureConsumer(FibreNodeFunction[Sequence[T], Mapping[FibreNode, T], CaptureEntryAction[T]]):
    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[Self, Sequence[T], Mapping[FibreNode, T], CaptureEntryAction[T]],
        previous_state: Optional[FibreNodeState[Self, Sequence[T], Mapping[FibreNode, T]]],
        enqueued_updates: Iterator[CaptureEntryAction[T]],
    ) -> FibreNodeState[Self, Sequence[T], Mapping[FibreNode, T]]:
        raise NotImplementedError()


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
        capture_consumer_node = FibreNode.create(
            key=CAPTURE_CONSUMER_KEY,
            parent=fibre_node,
            props_type=CaptureConsumer,
            fibre_node_function_type=CaptureConsumer,
        )

        context_map: dict[AbstractContextKey, FibreNode] = {self.capture_key: capture_consumer_node}
        child_fibre_node = FibreNode.create(
            key=self.child.key if self.child.key is not None else DEFAULT_CAPTURE_CHILD_KEY,
            parent=fibre_node,
            props_type=type(self.child),
            fibre_node_function_type=cast(Type[FibreNodeFunction], type(self.child)),
            contexts=fibre_node.contexts.new_child(context_map),
        )
        fibre.run(child_fibre_node, self.child)

        capture_consumer_result = fibre.run(capture_consumer_node, CaptureConsumer[T]())
        return FibreNodeState(
            props=self,
            result=capture_consumer_result.result,
            result_version=capture_consumer_result.result_version,
            state=None,
            children=(child_fibre_node, capture_consumer_node),
        )
