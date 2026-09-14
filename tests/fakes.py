from collections import deque
from copy import deepcopy
import json

from app.services.gemini_service import ProviderResult, Usage


def intent(actions=None, **kwargs):
    return ProviderResult(json.dumps({
        'actions': actions if actions is not None else [{'type': 'normal_chat'}],
        'needs_clarification': False, 'clarification_question': None, **kwargs,
    }), Usage(120, 45, 190))


def memory_result(candidates=None):
    return ProviderResult(json.dumps({
        'candidates': candidates or [],
    }), Usage(50, 15, 65))


def meal_image_result(meal_type='lunch', items=None, warnings=None, confidence='0.85'):
    return ProviderResult(json.dumps({
        'meal_type': meal_type,
        'items': items if items is not None else [{
            'name': 'Izgara Tavuk',
            'quantity': '180.00',
            'unit': 'g',
            'calories': '300.00',
            'protein_g': '55.00',
            'carbs_g': '0.00',
            'fat_g': '7.00',
        }],
        'warnings': warnings or ['Porsiyon miktarları fotoğraftan tahmin edilmiştir.'],
        'confidence': confidence,
    }), Usage(100, 50, 150))


class FakeGeminiProvider:
    model = 'fake-gemini'

    def __init__(self, intents=None, replies=None, memories=None, images=None):
        self.intents = deque(intents or [intent()])
        self.replies = deque(replies or [ProviderResult('Merhaba, yardımcı olabilirim.', Usage(210, 30, 270))])
        self.memories = deque(memories or [memory_result()])
        self.images = deque(images or [meal_image_result()])
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

    def generate_reply(self, payload, enable_search=False):
        payload_with_search = deepcopy(payload)
        payload_with_search['_enable_search'] = enable_search
        return self._respond('coach', payload_with_search, self.replies)

    def extract_memories(self, payload):
        return self._respond('memory', payload, self.memories)

    def analyze_meal_image(self, image_bytes, mime_type):
        return self._respond('image', {'mime_type': mime_type, 'size': len(image_bytes)}, self.images)

