from collections import deque
from copy import deepcopy
import json

from app.services.gemini_service import ProviderResult, Usage


def intent(actions=None, **kwargs):
    return ProviderResult(json.dumps({
        'actions': actions if actions is not None else [{'type': 'normal_chat'}],
        'needs_clarification': False, 'clarification_question': None, **kwargs,
    }), Usage(120, 45, 190))


class FakeGeminiProvider:
    model = 'fake-gemini'

    def __init__(self, intents=None, replies=None):
        self.intents = deque(intents or [intent()])
        self.replies = deque(replies or [ProviderResult('Merhaba, yardımcı olabilirim.', Usage(210, 30, 270))])
        self.calls = []
        self.on_call = None

    def _respond(self, phase, payload, results):
        self.calls.append((phase, deepcopy(payload)))
        if self.on_call:
            self.on_call(phase, payload)
        result = results.popleft()
        if isinstance(result, Exception):
            raise result
        return result

    def extract_intent(self, payload):
        return self._respond('intent', payload, self.intents)

    def generate_reply(self, payload):
        return self._respond('coach', payload, self.replies)
