"""Test configuration loading behavior."""

import stat

import pytest

from phantom.config import PhantomConfig


def test_load_returns_defaults_when_config_missing(tmp_path):
    config = PhantomConfig.load(str(tmp_path / "missing.toml"))
    assert (
        config.trust_level == "approve_new"
        and config.blocked_domains == ["bank", "medical"]
        and config.excluded_urls == ["bank", "medical"]
    )
    assert config.local_llm_helpers_enabled is False and config.neurovault_enabled is False


def test_load_reads_privacy_and_public_integration_overrides(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '''[privacy]\nexcluded_urls = ["bank", "medical", "internal"]\n\n[integrations]\nlocal_llm_helpers_enabled = true\nneurovault_enabled = true\nneurovault_base_dir = "/tmp/neurovault"\nrecipe_dir = "/tmp/recipes"\npattern_store = "/tmp/patterns.json"'''
    )
    config = PhantomConfig.load(str(config_file))
    assert config.blocked_domains == ["bank", "medical", "internal"] and config.excluded_urls == [
        "bank",
        "medical",
        "internal",
    ]
    assert (
        config.local_llm_helpers_enabled is True
        and config.neurovault_enabled is True
        and config.neurovault_base_dir == "/tmp/neurovault"
    )
    assert config.recipe_dir == "/tmp/recipes" and config.pattern_store == "/tmp/patterns.json"


def test_load_prefers_blocked_domains_key(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[privacy]\nblocked_domains = ["bank", "internal"]\nexcluded_urls = ["legacy"]'
    )
    config = PhantomConfig.load(str(config_file))
    assert config.blocked_domains == ["bank", "internal"] and config.excluded_urls == [
        "bank",
        "internal",
    ]


def test_llm_defaults_when_section_missing(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[phantom]\ntrust_level = "approve_new"\n')
    config = PhantomConfig.load(str(config_file))
    assert (
        config.llm_provider == "auto"
        and config.ollama_host == "http://localhost:11434"
        and config.llm_model == "auto"
    )
    assert (
        config.llm_temperature == 0.3
        and config.llm_max_tokens == 1024
        and config.llm_timeout == 30.0
        and config.llm_base_url == ""
        and config.llm_api_key == ""
    )


def test_llm_section_parsed(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[llm]\nprovider = "ollama"\nollama_host = "http://myhost:5555"\nmodel = "llama3.2:1b"\ntemperature = 0.7\nmax_tokens = 2048\ntimeout = 60\nbase_url = "http://alt:8080"\napi_key = "test-api-key"'
    )
    config = PhantomConfig.load(str(config_file))
    assert (
        config.llm_provider == "ollama"
        and config.ollama_host == "http://myhost:5555"
        and config.llm_model == "llama3.2:1b"
    )
    assert (
        config.llm_temperature == 0.7
        and config.llm_max_tokens == 2048
        and config.llm_timeout == 60.0
        and config.llm_base_url == "http://alt:8080"
        and config.llm_api_key == "test-api-key"
    )


def test_existing_config_is_restricted_to_owner(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[llm]\napi_key = "placeholder-value"\n')
    config_file.chmod(0o644)
    PhantomConfig.load(str(config_file))
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "body,error",
    [
        ('[phantom]\ntrust_level = "unknown"\n', "Invalid trust_level"),
        ("[phantom]\ncapture_fps = 0\n", "capture_fps must be > 0"),
        ("[phantom]\nmax_actions_per_minute = 0\n", "max_actions_per_minute must be > 0"),
    ],
)
def test_invalid_security_runtime_config_fails_closed(tmp_path, body, error):
    config_file = tmp_path / "config.toml"
    config_file.write_text(body)
    with pytest.raises(ValueError, match=error):
        PhantomConfig.load(str(config_file))
