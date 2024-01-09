import typing
from typing import Optional, Type

from attr import evolve, field, frozen
from typing_extensions import override

from pybt2.behaviour_tree.types import (
    BTNode,
    BTNodeResult,
    Children,
    Failure,
    Result,
    Running,
    Success,
    is_failure,
    is_success,
)
from pybt2.runtime.analysis import SupportsAnalysis
from pybt2.runtime.fibre import CallContext
from pybt2.runtime.types import FibreNodeFunction, Key


@frozen
class SequenceNode(BTNode, SupportsAnalysis):
    children: Children = field(repr=False)
    analysis_mode: bool = field(default=False, repr=False)

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        child_results: list[Result] = []
        for child in self.children:
            child_result = ctx.evaluate_child(child)
            if not is_success(child_result) and not self.analysis_mode:
                return child_result
            child_results.append(child_result)
        if self.analysis_mode:
            for child_result in child_results:
                if not is_success(child_result):
                    return child_result
        return Success([child_result.value for child_result in child_results])

    @classmethod
    @override
    def get_props_type_for_analysis(cls) -> Type[FibreNodeFunction]:
        return cls

    @override
    def get_props_for_analysis(self) -> FibreNodeFunction:
        return evolve(self, analysis_mode=True)


def Sequence(*children: BTNode, key: Optional[Key] = None) -> BTNode:
    return SequenceNode(children, key=key)  # type: ignore[arg-type]


AllOf = Sequence


@frozen
class FallbackNode(BTNode, SupportsAnalysis):
    children: Children = field(repr=False)
    analysis_mode: bool = field(default=False, repr=False)

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        child_results: list[Result] = []
        for child in self.children:
            child_result = ctx.evaluate_child(child)
            if not is_failure(child_result) and not self.analysis_mode:
                return child_result
            child_results.append(child_result)
        if self.analysis_mode:
            for child_result in child_results:
                if not is_failure(child_result):
                    return child_result
        return Failure([child_result.value for child_result in child_results])

    @classmethod
    @override
    def get_props_type_for_analysis(cls) -> Type[FibreNodeFunction]:
        return cls

    @override
    def get_props_for_analysis(self) -> FibreNodeFunction:
        return evolve(self, analysis_mode=True)


def Fallback(*children: BTNode, key: Optional[Key] = None) -> BTNode:
    return FallbackNode(children, key=key)  # type: ignore[arg-type]


AnyOf = Fallback


@frozen
class AlwaysSuccess(BTNode):
    value: typing.Any = None

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return Success(self.value)


@frozen
class AlwaysFailure(BTNode):
    value: typing.Any = None

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return Failure(self.value)


@frozen
class AlwaysRunning(BTNode):
    value: typing.Any = None

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return Running(self.value)


@frozen
class Always(BTNode):
    result: Result

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return self.result


@frozen
class PreconditionAction(BTNode):
    precondition: BTNode
    action: BTNode

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return ctx.evaluate_inline(SequenceNode([self.precondition, self.action]))


@frozen
class PostconditionPreconditionAction(BTNode):
    postcondition: BTNode
    actions: typing.Sequence[BTNode] = field(repr=False)

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return ctx.evaluate_inline(Fallback(self.postcondition, *self.actions))


@frozen
class Not(BTNode):
    child: BTNode

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        match ctx.evaluate_child(self.child):
            case Success(value):
                return Failure(value)
            case Failure(value):
                return Success(value)
            case _ as result:
                return result
