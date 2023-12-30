from abc import ABCMeta, abstractmethod
from typing import (
    Generic,
    Iterator,
    Mapping,
    MutableMapping,
    MutableSequence,
    Optional,
    Sequence,
    Type,
    cast,
    final,
)

from attr import mutable
from typing_extensions import Self

from pybt2.runtime.exceptions import (
    ChildAlreadyExistsError,
)
from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.types import (
    NO_CHILDREN,
    NO_PREDECESSORS,
    AbstractContextKey,
    FibreNodeFunction,
    FibreNodeState,
    Key,
    PropsT,
    ResultT,
    StateT,
    UpdateT,
)


@mutable(eq=False, weakref_slot=False)
class CallContext:
    fibre: Fibre
    fibre_node: FibreNode
    _previous_state: Optional[FibreNodeState]
    _pointer: int = 0
    _current_predecessors: Optional[MutableSequence[FibreNode]] = None
    _current_children: Optional[MutableSequence[FibreNode]] = None
    _current_tree_structure_predecessors: Optional[MutableSequence[FibreNode]] = None

    def add_predecessor(self, fibre_node: FibreNode) -> None:
        if self._current_predecessors is None:
            self._current_predecessors = [fibre_node]
        else:
            self._current_predecessors.append(fibre_node)

    def add_child(self, fibre_node: FibreNode) -> None:
        if self._current_children is None:
            self._current_children = [fibre_node]
        else:
            self._current_children.append(fibre_node)

    def _validate_child_key_is_unique(self, key: Key) -> None:
        if self._current_children is None:
            return
        for child in self._current_children:
            if child.key == key:
                raise ChildAlreadyExistsError(key, existing_child=child)

    def _next_child_key(self, optional_key: Optional[Key]) -> Key:
        if optional_key is not None:
            self._validate_child_key_is_unique(optional_key)
        self._pointer += 1
        return optional_key if optional_key is not None else self._pointer

    def _get_previous_child_with_key(self, key: Key) -> Optional[FibreNode]:
        if self._previous_state is not None:
            for child in self._previous_state.children:
                if child.key == key:
                    return child
        return None

    def _get_child_fibre_node(
        self,
        props_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]],
        key: Optional[Key] = None,
        additional_contexts: Optional[Mapping[AbstractContextKey, FibreNode]] = None,
    ) -> FibreNode[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT, UpdateT]:
        child_key = self._next_child_key(key)
        previous_child_fibre_node: Optional[FibreNode] = self._get_previous_child_with_key(child_key)
        if previous_child_fibre_node is not None and previous_child_fibre_node.props_type is props_type:
            return previous_child_fibre_node
        else:
            return FibreNode(
                key=child_key,
                parent=self.fibre_node,
                props_type=props_type,
                contexts=self.fibre_node.contexts.new_child(
                    cast(MutableMapping[AbstractContextKey, FibreNode], additional_contexts)
                )
                if additional_contexts is not None
                else self.fibre_node.contexts,
            )

    def evaluate_child(
        self,
        props: FibreNodeFunction[ResultT, StateT, UpdateT],
        key: Optional[Key] = None,
        additional_contexts: Optional[Mapping[AbstractContextKey, FibreNode]] = None,
    ) -> ResultT:
        child_fibre_node = self._get_child_fibre_node(
            type(props), key=key if key is not None else props.key, additional_contexts=additional_contexts
        )
        self.add_child(child_fibre_node)
        child_fibre_node_state = self.fibre.run(child_fibre_node, props)
        return child_fibre_node_state.result

    def _get_current_predecessors(self) -> Sequence[FibreNode]:
        if self._current_predecessors is None:
            return NO_PREDECESSORS
        else:
            return tuple(self._current_predecessors)

    def _get_current_children(self) -> Sequence[FibreNode]:
        if self._current_children is None:
            return NO_CHILDREN
        else:
            return tuple(self._current_children)

    def _get_current_tree_structure_predecessors(self) -> Sequence[FibreNode]:
        if self._current_tree_structure_predecessors is None:
            return NO_PREDECESSORS
        else:
            return tuple(self._current_tree_structure_predecessors)

    def get_last_child(self) -> FibreNode:
        if self._current_children is None:
            raise IndexError()
        return self._current_children[-1]

    def create_fibre_node_state(
        self, props: PropsT, result: ResultT, state: StateT
    ) -> FibreNodeState[PropsT, ResultT, StateT]:
        next_result_version: int
        if self._previous_state is not None:
            next_result_version = (
                self._previous_state.result_version
                if result == self._previous_state.result
                else self._previous_state.result_version + 1
            )
        else:
            next_result_version = 1
        return FibreNodeState(
            props=props,
            result=result,
            result_version=next_result_version,
            state=state,
            predecessors=self._get_current_predecessors(),
            children=self._get_current_children(),
            tree_structure_predecessors=self._get_current_tree_structure_predecessors(),
        )


class RuntimeCallableProps(FibreNodeFunction[ResultT, None, None], Generic[ResultT], metaclass=ABCMeta):
    @abstractmethod
    def __call__(self, ctx: CallContext) -> ResultT:
        ...

    @final
    def run(
        self,
        fibre: "Fibre",
        fibre_node: "FibreNode[Self, ResultT, None, None]",
        previous_state: Optional["FibreNodeState[Self, ResultT, None]"],
        enqueued_updates: Iterator[None],
    ) -> "FibreNodeState[Self, ResultT, None]":
        ctx = CallContext(fibre=fibre, fibre_node=fibre_node, previous_state=previous_state)

        result = self(ctx)

        return ctx.create_fibre_node_state(self, result, None)
