import pytest

from pybt2.behaviour_tree.nodes import AlwaysFailure, AlwaysRunning, AlwaysSuccess
from pybt2.behaviour_tree.types import (
    BTNode,
    BTNodeResult,
    Failure,
    Result,
    Running,
    Success,
    is_failure,
    is_running,
    is_success,
)
from pybt2.runtime.fibre import CallContext, Fibre, FibreNode
from tests.behaviour_tree.utils import run_node_in_fibre


def test_is_success():
    assert is_success(Success())
    assert not is_success(Running())
    assert not is_success(Failure())


def test_is_failure():
    assert is_failure(Failure())
    assert not is_failure(Success())
    assert not is_failure(Running())


def test_is_running():
    assert is_running(Running())
    assert not is_running(Success())
    assert not is_running(Failure())


@pytest.mark.parametrize(
    ("node_return", "expected"), [(True, Success()), (False, Failure())], ids=["return=True", "return=False"]
)
def test_can_return_bool(node_return: bool, expected: Result, fibre: Fibre, root_fibre_node: FibreNode):
    @run_node_in_fibre(fibre, root_fibre_node)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return node_return

    assert execute.result == expected


@pytest.mark.parametrize(
    ("node_return", "expected"),
    [(AlwaysSuccess(), Success()), (AlwaysFailure(), Failure()), (AlwaysRunning(), Running())],
    ids=["AlwaysSuccess", "AlwaysFailure", "AlwaysRunning"],
)
def test_can_return_node(node_return: BTNode, expected: Result, fibre: Fibre, root_fibre_node: FibreNode):
    @run_node_in_fibre(fibre, root_fibre_node)
    def execute(_ctx: CallContext) -> BTNodeResult:
        return node_return

    assert execute.result == expected
