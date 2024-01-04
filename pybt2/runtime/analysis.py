from abc import ABCMeta, abstractmethod
from typing import Mapping, Optional, Type

from attr import frozen
from typing_extensions import override

from pybt2.runtime.fibre import CallContext, CallContextFactory, Fibre, FibreNode
from pybt2.runtime.types import (
    AbstractContextKey,
    FibreNodeFunction,
    FibreNodeState,
    Key,
    PropsT,
    ResultT,
    StateT,
    UpdateT,
)


class SupportsAnalysis(FibreNodeFunction, metaclass=ABCMeta):
    @classmethod
    @abstractmethod
    def get_props_type_for_analysis(cls) -> Type[FibreNodeFunction]:
        ...

    @abstractmethod
    def get_props_for_analysis(self) -> FibreNodeFunction:
        ...


@frozen
class CallContextForAnalysis(CallContext):
    ctx: CallContext

    @property
    @override
    def fibre(self) -> Fibre:
        return self.ctx.fibre

    @property
    @override
    def fibre_node(self) -> FibreNode:
        return self.ctx.fibre_node

    @override
    def add_predecessor(self, fibre_node: FibreNode) -> None:
        return self.ctx.add_predecessor(fibre_node)

    @override
    def get_child_fibre_node(
        self,
        props_type: Type[FibreNodeFunction[ResultT, StateT, UpdateT]],
        key: Optional[Key] = None,
        additional_contexts: Optional[Mapping[AbstractContextKey, "FibreNode"]] = None,
    ) -> "FibreNode[FibreNodeFunction[ResultT, StateT, UpdateT], ResultT, StateT, UpdateT]":
        return self.ctx.get_child_fibre_node(
            props_type.get_props_type_for_analysis() if issubclass(props_type, SupportsAnalysis) else props_type,
            key,
            additional_contexts,
        )

    @override
    def evaluate_child(
        self,
        props: FibreNodeFunction[ResultT, StateT, UpdateT],
        key: Optional[Key] = None,
        additional_contexts: Optional[Mapping[AbstractContextKey, "FibreNode"]] = None,
    ) -> ResultT:
        return self.ctx.evaluate_child(
            props.get_props_for_analysis() if isinstance(props, SupportsAnalysis) else props, key, additional_contexts
        )

    @override
    def evaluate_inline(self, props: FibreNodeFunction[ResultT, None, None]) -> ResultT:
        return self.ctx.evaluate_inline(
            props.get_props_for_analysis() if isinstance(props, SupportsAnalysis) else props
        )

    @override
    def get_last_child(self) -> "FibreNode":
        return self.ctx.get_last_child()

    @override
    def create_fibre_node_state(
        self, props: PropsT, result: ResultT, state: StateT
    ) -> FibreNodeState[PropsT, ResultT, StateT]:
        return self.ctx.create_fibre_node_state(props, result, state)


@frozen
class AnalysisCallContextFactory(CallContextFactory):
    delegate: CallContextFactory

    def create_call_context(
        self,
        fibre: "Fibre",
        fibre_node: FibreNode,
        previous_state: Optional[FibreNodeState],
    ) -> CallContext:
        return CallContextForAnalysis(self.delegate.create_call_context(fibre, fibre_node, previous_state))
