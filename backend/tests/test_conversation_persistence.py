from __future__ import annotations

import asyncio
import uuid

from app.api.routes.conversations import _persist_assistant_message


class FakeConversation:
    def __init__(self, messages):
        self.messages = list(messages)


class FakeSession:
    def __init__(self, conversation):
        self.conversation = conversation
        self.committed = 0

    async def get(self, model, _obj_id):
        if model.__name__ == "Conversation":
            return self.conversation
        return None

    async def commit(self):
        self.committed += 1


def test_persist_assistant_message_appends_and_commits():
    conversation = FakeConversation([{"role": "user", "content": "hi"}])
    session = FakeSession(conversation)

    asyncio.run(_persist_assistant_message(session, uuid.uuid4(), "这是回答"))

    assert conversation.messages == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "这是回答"},
    ]
    assert session.committed == 1


def test_persist_assistant_message_missing_conversation_is_noop():
    session = FakeSession(None)

    asyncio.run(_persist_assistant_message(session, uuid.uuid4(), "这是回答"))

    assert session.committed == 0
