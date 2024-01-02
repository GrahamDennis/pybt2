from typing import Optional

from attr import frozen

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
from pybt2.runtime.fibre import CallContext
from pybt2.runtime.types import Key


@frozen
class SequenceNode(BTNode):
    children: Children

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        for child in self.children:
            result = ctx.evaluate_child(child)
            if not is_success(result):
                return result
        return Success()


def Sequence(*children: BTNode, key: Optional[Key] = None) -> BTNode:
    return SequenceNode(children, key=key)  # type: ignore[arg-type]


@frozen
class FallbackNode(BTNode):
    children: Children

    def __call__(self, ctx: CallContext) -> BTNodeResult:
        for child in self.children:
            result = ctx.evaluate_child(child)
            if not is_failure(result):
                return result
        return Failure()


def Fallback(*children: BTNode, key: Optional[Key] = None) -> BTNode:
    return FallbackNode(children, key=key)  # type: ignore[arg-type]


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
