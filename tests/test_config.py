import pytest
from config import load_config, Config


def test_load_config():
    config = load_config()
    assert isinstance(config, Config)
    assert config.sr_prefixes == ["STH", "STP", "SFQ", "SWH", "SXM", "SBJ", "SQD"]
    assert config.message_table == "ims_message"
    assert config.required_locale == "en_US"
    assert config.llm_enabled is True
    assert config.ollama_url == "http://localhost:11434"
    assert config.llm_timeout_seconds == 30
    assert config.teams_webhook_url_env == "TEAMS_WEBHOOK_URL"
    assert config.browser_profile_dir == "browser-profile"
    assert config.login_timeout_seconds == 300
    assert config.teams_pacing_delay_ms == 500
    assert config.teams_max_retries == 3