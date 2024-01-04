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
        if self.analysis_mode:
            return self.evaluate_in_analysis_mode(ctx)
        for child in self.children:
            result = ctx.evaluate_child(child)
            if not is_success(result):
                return result
        return Success()

    def evaluate_in_analysis_mode(self, ctx: CallContext) -> BTNodeResult:
        results: list[Result] = []
        for child in self.children:
            results.append(ctx.evaluate_child(child))

        for result in results:
            if not is_success(result):
                return result
        return Success()

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
        if self.analysis_mode:
            return self.evaluate_in_analysis_mode(ctx)
        for child in self.children:
            result = ctx.evaluate_child(child)
            if not is_failure(result):
                return result
        return Failure()

    def evaluate_in_analysis_mode(self, ctx: CallContext) -> BTNodeResult:
        results: list[Result] = []
        for child in self.children:
            results.append(ctx.evaluate_child(child))

        for result in results:
            if not is_failure(result):
                return result
        return Success()

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
    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return Success()


@frozen
class AlwaysFailure(BTNode):
    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return Failure()


@frozen
class AlwaysRunning(BTNode):
    def __call__(self, ctx: CallContext) -> BTNodeResult:
        return Running()


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
