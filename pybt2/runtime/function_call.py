import operator
from typing import TYPE_CHECKING, Callable, Generic, Optional, Sequence

from attr import frozen

from pybt2.runtime.fibre import CallFrameType
from pybt2.runtime.types import CallFrameResult, ExecutingCallFrame, PropsT, ResultT

if TYPE_CHECKING:
    from .fibre import Fibre


@frozen
class FunctionCallFrameType(CallFrameType[PropsT, ResultT, None, None], Generic[PropsT, ResultT]):
    _fn: Callable[[ExecutingCallFrame, PropsT], ResultT]
    _props_eq: Callable[[PropsT, PropsT], bool] = operator.eq
    _result_eq: Callable[[ResultT, ResultT], bool] = operator.eq

    def display_name(self) -> str:
        return self._fn.__qualname__

    def are_props_equal(self, left: PropsT, right: PropsT) -> bool:
        return self._props_eq(left, right)

    def run(
        self,
        fibre: "Fibre",
        props: PropsT,
        previous_result: Optional[CallFrameResult[ResultT, None]],
        _enqueued_updates: Optional[Sequence[None]],
    ) -> CallFrameResult[ResultT, None]:
        ctx = ExecutingCallFrame()

        result = self._fn(ctx, props)
        next_result_version: int
        if previous_result is None:
            next_result_version = 1
        elif self._result_eq(result, previous_result.result):
            next_result_version = previous_result.result_version
        else:
            next_result_version = previous_result.result_version + 1

        return CallFrameResult(
            result=result,
            state=None,
            result_version=next_result_version,
            predecessors=ctx.get_predecessors(),
        )

    def dispose(self, result: CallFrameResult[ResultT, None]) -> None:
        pass
