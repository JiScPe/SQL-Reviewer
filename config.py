import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import List


@dataclass
class Config:
    sr_prefixes: List[str]
    message_table: str
    required_locale: str
    llm_enabled: bool
    ollama_url: str
    llm_timeout_seconds: int
    teams_webhook_url_env: str
    browser_profile_dir: str
    login_timeout_seconds: int
    teams_pacing_delay_ms: int
    teams_max_retries: int
    kdocs_base_url: str
    kdocs_sheet_url: str


def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Config(
        sr_prefixes=data["sr_prefixes"],
        message_table=data["message_table"],
        required_locale=data["required_locale"],
        llm_enabled=data["llm_enabled"],
        ollama_url=data["ollama_url"],
        llm_timeout_seconds=data["llm_timeout_seconds"],
        teams_webhook_url_env=data["teams_webhook_url_env"],
        browser_profile_dir=data["browser_profile_dir"],
        login_timeout_seconds=data["login_timeout_seconds"],
        teams_pacing_delay_ms=data["teams_pacing_delay_ms"],
        teams_max_retries=data["teams_max_retries"],
        kdocs_base_url=data.get("kdocs_base_url", "https://www.kdocs.cn"),
        kdocs_sheet_url=data.get("kdocs_sheet_url", "https://www.kdocs.cn"),
    )


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config