import asyncio
from typing import AsyncIterator, Collection

import pytest
import pytest_asyncio
from aiotools import VirtualClock

from pybt2.runtime.fibre import Fibre, FibreNode
from pybt2.runtime.types import Key

from .utils import ExternalFunctionProps

# This is necessary to get pretty assertion failure messages from the test instrumentation module
pytest.register_assert_rewrite("tests.instrumentation")

from .instrumentation import CallRecordingInstrumentation  # noqa: E402


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


@pytest.fixture()
def root_fibre_node() -> FibreNode:
    return FibreNode(key="root", parent=None, props_type=ExternalFunctionProps)


@pytest_asyncio.fixture()
async def virtual_clock() -> AsyncIterator[VirtualClock]:
    virtual_clock = VirtualClock()
    with virtual_clock.patch_loop():
        yield virtual_clock
        # Ensure any pending cancellations are run
        await asyncio.sleep(1)
