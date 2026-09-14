from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors, types

from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.intents import IntentPlan
from app.services.gemini_service import GoogleGeminiProvider, ProviderError, wire_schema
from tests.fakes import intent


class StubClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.models = self
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def install_stub(monkeypatch, outcome):
    stub = StubClient(outcome)
    options = {}
    def factory(**kwargs):
        options.update(kwargs)
        return stub
    monkeypatch.setattr('app.services.gemini_service.genai.Client', factory)
    settings = Settings(_env_file=None, gemini_api_key='not-a-real-secret', gemini_model='test-model')
    return GoogleGeminiProvider(settings), stub, options


def test_official_sdk_config_usage_and_structured_wire_schema(monkeypatch):
    response = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=[types.Part(text=intent().text)]))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=10, candidates_token_count=4, total_token_count=20),
    )
    provider, stub, options = install_stub(monkeypatch, response)
    result = provider.extract_intent({'current_message': 'Merhaba'})
    assert IntentPlan.model_validate_json(result.text).actions[0].type == 'normal_chat'
    assert result.usage.input_tokens == 10 and result.usage.output_tokens == 4 and result.usage.total_tokens == 20
    assert options['vertexai'] is False
    assert options['http_options'].timeout == 30000
    assert options['http_options'].retry_options.attempts == 1
    config = stub.calls[0]['config']
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_mime_type == 'application/json'
    assert config.response_json_schema == wire_schema()
    assert 'discriminator' not in str(wire_schema()) and 'oneOf' not in str(wire_schema()) and 'maxItems' not in str(wire_schema())
    provider.generate_reply({'today': {'totals': None}})
    assert stub.calls[-1]['config'].response_json_schema is None


@pytest.mark.parametrize('error,kind', [
    (httpx.ReadTimeout('secret value'), 'timeout'),
    (httpx.ConnectError('secret value'), 'network'),
    (errors.APIError(401, {'error': {'message': 'secret value'}}), 'authentication'),
    (errors.APIError(403, {'error': {'message': 'secret value'}}), 'authentication'),
    (errors.APIError(400, {'error': {'details': [{'reason': 'API_KEY_INVALID'}], 'message': 'secret value'}}), 'authentication'),
    (errors.APIError(429, {'error': {'message': 'secret value'}}), 'rate_limit'),
    (errors.APIError(404, {'error': {'message': 'secret value'}}), 'model_unavailable'),
    (errors.APIError(503, {'error': {'message': 'secret value'}}), 'model_unavailable'),
    (errors.APIError(504, {'error': {'message': 'secret value'}}), 'timeout'),
    (errors.APIError(500, {'error': {'message': 'secret value'}}), 'provider_error'),
    (RuntimeError('secret value'), 'provider_error'),
])
def test_error_mapping_never_returns_raw_provider_error(monkeypatch, error, kind):
    provider, _, _ = install_stub(monkeypatch, error)
    with pytest.raises(ProviderError) as caught:
        provider.extract_intent({})
    assert caught.value.kind == kind
    assert 'secret value' not in str(caught.value)


def test_missing_usage_is_unknown_not_zero(monkeypatch):
    provider, _, _ = install_stub(monkeypatch, SimpleNamespace(text='Merhaba', usage_metadata=None))
    result = provider.generate_reply({})
    assert result.usage.input_tokens is None
    assert result.usage.total_tokens is None


def test_missing_configuration_does_not_open_client(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('NUTRICOACH_GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    monkeypatch.delenv('NUTRICOACH_GEMINI_MODEL', raising=False)
    def fail(**kwargs):
        pytest.fail('Eksik ayarla ağ istemcisi açılmamalı.')
    monkeypatch.setattr('app.services.gemini_service.genai.Client', fail)
    with pytest.raises(ProviderError, match='configuration'):
        GoogleGeminiProvider(Settings(_env_file=None)).extract_intent({})


def test_config_supports_existing_and_new_env_names(monkeypatch):
    for name in ('GEMINI_API_KEY', 'GEMINI_MODEL', 'NUTRICOACH_GEMINI_API_KEY', 'NUTRICOACH_GEMINI_MODEL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('NUTRICOACH_GEMINI_API_KEY', 'legacy-key')
    monkeypatch.setenv('NUTRICOACH_GEMINI_MODEL', 'legacy-model')
    config = Settings(_env_file=None)
    assert config.gemini_api_key.get_secret_value() == 'legacy-key'
    assert config.gemini_model == 'legacy-model'
    monkeypatch.setenv('GEMINI_API_KEY', 'new-key')
    monkeypatch.setenv('GEMINI_MODEL', 'new-model')
    config = Settings(_env_file=None)
    assert config.gemini_api_key.get_secret_value() == 'new-key'
    assert 'new-key' not in repr(config)
    assert config.gemini_model == 'new-model'


def test_wire_schema_excludes_max_items_while_pydantic_enforces_bounds():
    schema = wire_schema()

    def has_key(obj, key):
        if isinstance(obj, dict):
            return key in obj or any(has_key(v, key) for v in obj.values())
        if isinstance(obj, list):
            return any(has_key(item, key) for item in obj)
        return False

    assert not has_key(schema, 'maxItems')
    assert has_key(schema, 'minItems')
    assert has_key(schema, 'minLength')
    assert has_key(schema, 'maxLength')

    with pytest.raises(ValidationError):
        IntentPlan.model_validate({
            'actions': [{'type': 'normal_chat'}] * 6,
            'needs_clarification': False,
            'clarification_question': None,
        })

