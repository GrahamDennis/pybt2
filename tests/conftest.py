import asyncio
import gc
import weakref
from typing import AsyncIterator, Callable, Collection, Iterator, Type, cast

import pytest
import pytest_asyncio
from aiotools import VirtualClock

from pybt2.runtime import static_configuration

# This is necessary to enable testing that there are no dangling references to objects
static_configuration.ENABLE_WEAK_REFERENCE_SUPPORT = True

# This is necessary to get pretty assertion failure messages from the test instrumentation module
pytest.register_assert_rewrite("tests.instrumentation")

from pybt2.runtime.fibre import CallContext, Fibre, FibreNode  # noqa: E402
from pybt2.runtime.types import FibreNodeFunction, Key, ResultT  # noqa: E402

from .instrumentation import CallRecordingInstrumentation  # noqa: E402
from .utils import ExternalFunctionProps  # noqa: E402


@pytest.fixture()
def known_keys(request: pytest.FixtureRequest) -> Collection[Key]:
    marker = request.node.get_closest_marker("known_keys")
    if marker is None:
        return ()
    return tuple(marker.args)


@pytest.fixture()
def test_instrumentation(known_keys: Collection[Key]) -> CallRecordingInstrumentation:
    return CallRecordingInstrumentation(known_keys=known_keys)


@pytest.fixture(params=[False, True], ids=["incremental=False", "incremental=True"])
def fibre(test_instrumentation: CallRecordingInstrumentation, request: pytest.FixtureRequest) -> Fibre:
    return Fibre(instrumentation=test_instrumentation, incremental=request.param)


def _get_child_node_refs(fibre_node: FibreNode) -> Iterator[weakref.ReferenceType]:
    if (fibre_node_state := fibre_node.get_fibre_node_state()) is None:
        return
    for child in fibre_node_state.children:
        yield weakref.ref(child)
        yield from _get_child_node_refs(child)


def create_root_fibre_node(fibre: Fibre, root_fibre_node_props_type: Type[FibreNodeFunction]) -> Iterator[FibreNode]:
    root_fibre_node: FibreNode = FibreNode(key="root", parent=None, props_type=root_fibre_node_props_type)
    yield root_fibre_node

    node_refs = list(_get_child_node_refs(root_fibre_node))

    fibre.run(
        root_fibre_node,
        cast(Callable[[Callable[[CallContext], ResultT]], FibreNodeFunction], root_fibre_node_props_type)(
            lambda _ctx: None
        ),
    )
    fibre.drain_work_queue()

    for node_ref in node_refs:
        if (node := node_ref()) is not None:
            assert len(gc.get_referrers(node)) == 0


@pytest.fixture()
def root_fibre_node(fibre: Fibre) -> Iterator[FibreNode]:
    yield from create_root_fibre_node(fibre, ExternalFunctionProps)


@pytest_asyncio.fixture()
async def virtual_clock() -> AsyncIterator[VirtualClock]:
    virtual_clock = VirtualClock()
    with virtual_clock.patch_loop():
        yield virtual_clock
        # Ensure any pending cancellations are run
        await asyncio.sleep(1)
