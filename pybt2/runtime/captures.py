from typing import Generic, Iterator, Mapping, MutableMapping, Optional, Type, TypeVar, cast

from attr import frozen
from typing_extensions import Self

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.types import (
    AbstractContextKey,
    CaptureKey,
    FibreNodeFunction,
    FibreNodeState,
    Key,
)

T = TypeVar("T")

DEFAULT_CAPTURE_CHILD_KEY = "__CaptureRoot.Child"
CAPTURE_CONSUMER_KEY = "__CaptureRoot.Consumer"


@frozen(weakref_slot=False)
class AddCaptureEntry(Generic[T]):
    fibre_node: FibreNode
    value: T


@frozen(weakref_slot=False)
class RemoveCaptureEntry:
    fibre_node: FibreNode


CaptureEntryAction = AddCaptureEntry[T] | RemoveCaptureEntry


@frozen(weakref_slot=False)
class CaptureConsumer(FibreNodeFunction[Mapping[FibreNode, T], None, CaptureEntryAction[T]]):
    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[Self, Mapping[FibreNode, T], None, CaptureEntryAction[T]],
        previous_state: Optional[FibreNodeState[Self, Mapping[FibreNode, T], None]],
        enqueued_updates: Iterator[CaptureEntryAction[T]],
    ) -> FibreNodeState[Self, Mapping[FibreNode, T], None]:
        captures: MutableMapping[FibreNode, T] = {**previous_state.result} if previous_state is not None else {}
        for update in enqueued_updates:
            match update:
                case AddCaptureEntry(fibre_node, value):
                    captures[fibre_node] = value
                case RemoveCaptureEntry(fibre_node):
                    del captures[fibre_node]
        return FibreNodeState(
            props=self,
            result=captures,
            result_version=previous_state.result_version + 1 if previous_state is not None else 1,
            state=None,
        )


@frozen(weakref_slot=False)
class CaptureRoot(FibreNodeFunction[Mapping[FibreNode, T], None, None], Generic[T]):
    capture_key: CaptureKey[T]
    child: FibreNodeFunction

    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[Self, Mapping[FibreNode, T], None, None],
        previous_state: Optional[FibreNodeState[Self, Mapping[FibreNode, T], None]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, Mapping[FibreNode, T], None]:
        child_fibre_node: FibreNode
        capture_consumer_node: FibreNode[CaptureConsumer, Mapping[FibreNode, T], None, CaptureEntryAction[T]]

        if previous_state is not None:
            child_fibre_node, capture_consumer_node = previous_state.children
        else:
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


@frozen(weakref_slot=False)
class CaptureProviderState(Generic[T]):
    capture_provider_fibre_node: FibreNode
    capture_consumer_fibre_node: FibreNode[CaptureConsumer, Mapping[FibreNode, T], None, CaptureEntryAction[T]]
    fibre: Fibre


@frozen(weakref_slot=False)
class CaptureProvider(FibreNodeFunction[None, CaptureProviderState[T], None], Generic[T]):
    capture_consumer_fibre_node: FibreNode[CaptureConsumer, Mapping[FibreNode, T], None, CaptureEntryAction[T]]
    value: T

    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[Self, None, CaptureProviderState[T], None],
        previous_state: Optional[FibreNodeState[Self, None, CaptureProviderState[T]]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, None, CaptureProviderState[T]]:
        if previous_state is None or previous_state.props.value != self.value:
            self.capture_consumer_fibre_node.enqueue_update(AddCaptureEntry(fibre_node, self.value), fibre)

        return FibreNodeState(
            props=self,
            result=None,
            result_version=1,
            state=CaptureProviderState(
                capture_provider_fibre_node=fibre_node,
                capture_consumer_fibre_node=self.capture_consumer_fibre_node,
                fibre=fibre,
            ),
        )

    @classmethod
    def dispose(cls, state: FibreNodeState[Self, None, CaptureProviderState[T]]) -> None:
        capture_provider_state = state.state
        capture_provider_state.capture_consumer_fibre_node.enqueue_update(
            RemoveCaptureEntry(capture_provider_state.capture_provider_fibre_node), capture_provider_state.fibre
        )


def use_capture(ctx: CallContext, capture_key: CaptureKey[T], value: T, key: Optional[Key] = None) -> None:
    capture_consumer_fibre_node = cast(
        FibreNode[CaptureConsumer, Mapping[FibreNode, T], None, CaptureEntryAction[T]],
        ctx.get_fibre_node_for_context_key(capture_key),
    )
    ctx.evaluate_child(CaptureProvider(capture_consumer_fibre_node, value), key=key)
