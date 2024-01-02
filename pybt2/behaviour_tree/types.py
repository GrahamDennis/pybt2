from abc import ABCMeta, abstractmethod
from typing import Any, Iterator, Optional, Sequence, TypeGuard, Union, final

from attr import frozen
from typing_extensions import Self

from pybt2.runtime.fibre import CallContext
from pybt2.runtime.types import FibreNodeFunction, FibreNodeState


@frozen
class Success:
    value: Optional[Any] = None


@frozen
class Running:
    value: Optional[Any] = None  # A progress value?


@frozen
class Failure:
    value: Optional[Any] = None


Result = Success | Running | Failure


def is_success(result: Result) -> TypeGuard[Success]:
    return isinstance(result, Success)


def is_running(result: Result) -> TypeGuard[Running]:
    return isinstance(result, Running)


def is_failure(result: Result) -> TypeGuard[Failure]:
    return isinstance(result, Failure)


BTNodeResult = Union[Result, bool, "BTNode"]

_SUCCESS_INSTANCE = Success()
_FAILURE_INSTANCE = Failure()
_RUNNING_INSTANCE = Running()


@frozen
class BTNode(FibreNodeFunction[Result, None, None], metaclass=ABCMeta):
    @abstractmethod
    def __call__(self, ctx: CallContext) -> BTNodeResult:
        ...

    @final
    def run(
        self,
        ctx: CallContext,
        previous_state: Optional[FibreNodeState[Self, Result, None]],
        enqueued_updates: Iterator[None],
    ) -> FibreNodeState[Self, Result, None]:
        result = self(ctx)
        converted_result: Result
        match result:
            case bool():
                converted_result = _SUCCESS_INSTANCE if result else _FAILURE_INSTANCE
            case BTNode():
                converted_result = ctx.evaluate_child(result)
            case _:
                converted_result = result
        return ctx.create_fibre_node_state(self, converted_result, None)


Children = Sequence[BTNode]
