from typing import Any, Generic, Iterator, Optional, Type, TypeVar, cast

from attr import frozen
from typing_extensions import Self

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.function_call import CallContext
from pybt2.runtime.types import NO_PREDECESSORS, ContextKey, FibreNodeFunction, FibreNodeState, ResultT

T = TypeVar("T")

DEFAULT_CONTEXT_CHILD_KEY = "__ContextProvider.Child"


def _context_value_key(context_key: ContextKey[T]) -> str:
    return f"__ContextProvider.Value.{context_key.name}"


@frozen
class ContextValue(FibreNodeFunction[T, None, None], Generic[T]):
    value: T

    def run(
        self,
        fibre: "Fibre",
        fibre_node: FibreNode[Self, T, None, None],
        previous_state: Optional[FibreNodeState[Self, T, None]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, T, None]:
        result_version: int
        if previous_state is not None:
            result_version = (
                previous_state.result_version
                if self.value == previous_state.props.value
                else previous_state.result_version + 1
            )
        else:
            result_version = 1
        return FibreNodeState(
            props=self, result=self.value, result_version=result_version, state=None, predecessors=NO_PREDECESSORS
        )


@frozen
class ContextProvider(FibreNodeFunction[ResultT, None, None], Generic[T, ResultT]):
    context_key: ContextKey[T]
    value: T
    child: FibreNodeFunction[ResultT, Any, Any]

    def run(
        self,
        fibre: Fibre,
        fibre_node: FibreNode[Self, ResultT, None, None],
        previous_state: Optional[FibreNodeState[Self, ResultT, None]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, ResultT, None]:
        if previous_state is not None:
            context_value_node = cast(FibreNode[ContextValue[T], T, None, None], previous_state.predecessors[0])
            previous_child_node = cast(
                FibreNode[FibreNodeFunction[ResultT, Any, Any], ResultT, Any, Any],
                previous_state.predecessors[1],
            )
            fibre.run(context_value_node, ContextValue(self.value))

            previous_child_result = previous_child_node.get_fibre_node_state()

            if (
                previous_child_node.props_type is type(self.child)
                and previous_child_result is not None
                and previous_child_result.props.key == self.child.key
            ):
                child_result = fibre.run(previous_child_node, self.child)
                return FibreNodeState(
                    props=self,
                    result=child_result.result,
                    result_version=previous_state.result_version
                    if child_result.result_version == previous_child_result.result_version
                    else previous_state.result_version + 1,
                    state=None,
                    predecessors=previous_state.predecessors,
                )
        context_value_node = FibreNode.create(
            key=_context_value_key(self.context_key),
            parent=fibre_node,
            props_type=ContextValue,
            fibre_node_function_type=ContextValue,
            contexts=fibre_node.contexts,
        )
        fibre.run(context_value_node, ContextValue(self.value))
        context_map = {self.context_key: context_value_node}
        child_fibre_node = FibreNode.create(
            key=self.child.key if self.child.key is not None else DEFAULT_CONTEXT_CHILD_KEY,
            parent=fibre_node,
            props_type=type(self.child),
            fibre_node_function_type=cast(Type[FibreNodeFunction[ResultT, Any, Any]], type(self.child)),
            contexts=fibre_node.contexts.new_child(context_map),
        )
        child_result = fibre.run(child_fibre_node, self.child)
        return FibreNodeState(
            props=self,
            result=child_result.result,
            result_version=previous_state.result_version + 1 if previous_state is not None else 1,
            state=None,
            predecessors=(
                context_value_node,
                child_fibre_node,
            ),
        )


def use_context(ctx: CallContext, context_key: ContextKey[T]) -> T:
    context_value_fibre_node = cast(
        FibreNode[ContextValue[T], T, None, None], ctx.get_context_value_fibre_node(context_key)
    )
    context_value_fibre_node_state = context_value_fibre_node.get_fibre_node_state()
    assert context_value_fibre_node_state is not None
    ctx.add_predecessor(context_value_fibre_node)
    return context_value_fibre_node_state.result
