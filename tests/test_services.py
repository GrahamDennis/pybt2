from typing import Mapping

import pytest
from attr import frozen

from pybt2.runtime.captures import UnorderedCaptureProvider
from pybt2.runtime.fibre import CallContext, Fibre, FibreNode
from pybt2.runtime.function_call import RuntimeCallableProps
from pybt2.runtime.hooks import AsyncResult, AsyncRunning, AsyncSuccess
from pybt2.runtime.services import ApiCall, use_api_call
from pybt2.runtime.types import CaptureKey
from tests.instrumentation import CallRecordingInstrumentation
from tests.utils import run_in_fibre


@frozen
class ExampleService:
    async def hello(self, name: str) -> str:
        return f"Hello {name}"


@pytest.mark.known_keys("capture-root", "use_api_call")
@pytest.mark.asyncio()
async def test_use_api_call(
    fibre: Fibre, root_fibre_node: FibreNode, test_instrumentation: CallRecordingInstrumentation
):
    @frozen
    class UseApiChild(RuntimeCallableProps[AsyncResult[str]]):
        def __call__(self, ctx: CallContext) -> AsyncResult[str]:
            return use_api_call(ctx, ExampleService.hello, "Wally", key="use_api_call")

    @run_in_fibre(fibre, root_fibre_node)
    def execute_1(ctx: CallContext) -> tuple[AsyncResult[str], Mapping[FibreNode, str]]:
        return ctx.evaluate_child(
            UnorderedCaptureProvider[AsyncResult[str], str](
                CaptureKey(ExampleService.hello), UseApiChild(key="use-api-child"), key="capture-root"
            )
        )

    use_api_node = root_fibre_node.get_fibre_node(("capture-root", "use-api-child", "use_api_call"))
    capture_leaf_node = use_api_node.get_fibre_node(("capture",))
    use_state_node = use_api_node.get_fibre_node((1,))

    test_instrumentation.assert_evaluations_and_reset(
        ("capture-root",),
        ("capture-root", "use_api_call"),
        ("capture-root",),
    )

    fibre_node_state = use_state_node.get_fibre_node_state()
    assert fibre_node_state is not None
    _, set_async_result = fibre_node_state.result
    assert execute_1.result == (
        AsyncRunning(),
        {capture_leaf_node: ApiCall(request="Wally", set_async_result=set_async_result)},
    )

    set_async_result(AsyncSuccess("Hello Wally"))
    assert use_state_node.is_out_of_date()

    if fibre.incremental:
        fibre.drain_work_queue()

        test_instrumentation.assert_evaluations_and_reset(("capture-root", "use_api_call"), ("capture-root",))

    @run_in_fibre(fibre, root_fibre_node)
    def execute_2(ctx: CallContext) -> tuple[AsyncResult[str], Mapping[FibreNode, str]]:
        return ctx.evaluate_child(
            UnorderedCaptureProvider[AsyncResult[str], str](
                CaptureKey(ExampleService.hello), UseApiChild(key="use-api-child"), key="capture-root"
            )
        )

    test_instrumentation.assert_evaluations_and_reset(
        *[
            ("capture-root",),
            ("capture-root", "use_api_call"),
            ("capture-root",),
        ]
        if not fibre.incremental
        else []
    )

    fibre_node_state = use_state_node.get_fibre_node_state()
    assert fibre_node_state is not None
    _, set_async_result = fibre_node_state.result
    assert execute_2.result == (
        AsyncSuccess("Hello Wally"),
        {capture_leaf_node: ApiCall(request="Wally", set_async_result=set_async_result)},
    )
