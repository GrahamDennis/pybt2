from typing import Generic, TypeVar

from attr import mutable

NodeT = TypeVar("NodeT")


@mutable
class DependencyGraph(Generic[NodeT]):
    pass

    # What is the right model for the dependency graph?
    # We have a function block with arguments (predecessor)
    # function calls / operations
    # Correct would be:
    # args => body 1 => child function call 1 => body 2 => child function call 2 => return value
