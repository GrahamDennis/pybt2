from typing import Iterator

import pytest

from pybt2.runtime.fibre import Fibre, FibreNode
from tests.behaviour_tree.utils import ExternalBTNode
from tests.conftest import create_root_fibre_node


@pytest.fixture()
def bt_root_fibre_node(fibre: Fibre) -> Iterator[FibreNode]:
    yield from create_root_fibre_node(fibre, ExternalBTNode)
