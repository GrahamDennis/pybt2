from typing import Generator

import pytest

from pybt2.runtime.scheduler import Scheduler


def fibonacci(n: int) -> Generator[Generator, int, int]:
    match n:
        case 0:
            return 0
        case 1:
            return 1
        case _:
            return (yield fibonacci(n - 1)) + (yield fibonacci(n - 2))


def assert_fibonacci(n: int, expected: int) -> Generator[Generator, int, None]:
    value = yield fibonacci(n)
    assert value == expected


@pytest.fixture()
def scheduler() -> Scheduler:
    return Scheduler()


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, 0),
        (1, 1),
        (6, 8),
    ],
)
def test_scheduler(n: int, expected: int, scheduler: Scheduler):
    scheduler.schedule(assert_fibonacci(n, expected))
    scheduler.run()


def test_failure(scheduler: Scheduler):
    def throw_exception() -> Generator:
        raise NotImplementedError()
        yield  # required to make this a generator

    def propagate_exception() -> Generator:
        yield throw_exception()

    scheduler.schedule(propagate_exception())
    with pytest.raises(NotImplementedError):
        scheduler.run()


def test_iterate(scheduler: Scheduler):
    def iterator() -> Generator:
        yield 1
        yield 2
        return 3

    def consume_iterator() -> Generator:
        it = iterator()
        assert (yield it) == 1
        assert (yield it) == 2
        assert (yield it) == 3

    scheduler.schedule(consume_iterator())
    scheduler.run()
