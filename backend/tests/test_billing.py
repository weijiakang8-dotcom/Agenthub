import asyncio
import uuid
from types import SimpleNamespace

from app.core import billing
from app.core.billing import estimate_tokens


def test_estimate_tokens_positive():
    assert estimate_tokens("hello world") > 0
    assert estimate_tokens("") == 0


def test_estimate_tokens_monotonic():
    assert estimate_tokens("a" * 400) >= estimate_tokens("a" * 40)


def test_record_usage_costs_by_actual_model(monkeypatch):
    execution = SimpleNamespace(
        id=uuid.uuid4(),
        input_tokens=0,
        output_tokens=0,
        cost=0.0,
        organization_id=uuid.uuid4(),
        user_input="q",
        final_output="a",
        error_message=None,
        checkpoint_data={
            "llm_usage": [
                {
                    "model_used": "deepseek-v4-flash",
                    "input_tokens": 1000,
                    "output_tokens": 1000,
                    "fallback": True,
                    "attempts": 1,
                }
            ]
        },
    )

    class FakeResult:
        def scalars(self):
            return self

        def first(self):
            return None

        def all(self):
            return [
                SimpleNamespace(
                    model="deepseek-v4-flash",
                    cost_per_1k_tokens=0.001,
                    organization_id=None,
                )
            ]

    class FakeSession:
        async def get(self, _model, _obj_id):
            return execution

        async def execute(self, _stmt):
            return FakeResult()

        async def commit(self):
            return None

    class FakeFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(billing, "async_session_factory", FakeFactory())

    asyncio.run(billing.record_execution_usage(execution.id))

    assert execution.input_tokens == 1000
    assert execution.output_tokens == 1000
    assert execution.cost == 0.002
