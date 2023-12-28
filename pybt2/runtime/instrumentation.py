from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING

from attr import frozen

if TYPE_CHECKING:
    from .fibre import FibreNode


class FibreInstrumentation(metaclass=ABCMeta):
    @abstractmethod
    def on_node_evaluation_start(self, fibre_node: "FibreNode") -> None:
        ...

    @abstractmethod
    def on_node_evaluation_end(self, fibre_node: "FibreNode") -> None:
        ...


@frozen
class NoOpFibreInstrumentation(FibreInstrumentation):
    def on_node_evaluation_start(self, fibre_node: "FibreNode") -> None:  # pragma: no cover
        pass

    def on_node_evaluation_end(self, fibre_node: "FibreNode") -> None:  # pragma: no cover
        pass
