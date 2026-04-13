"""
Central config — reads from environment / .env file.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # OpenAI
    openai_api_key:  str = ""
    openai_model:    str = "gpt-4o"

    # GitHub
    github_token:    str = ""
    github_username: str = ""

    # Docker sandbox
    docker_image:    str = "python:3.11-slim"
    sandbox_timeout: int = 60  # seconds

    # Agent behaviour
    max_retries:     int = 3
    workspace_dir:   str = "/tmp/ai-agent-workspace"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            openai_api_key  = os.environ.get("OPENAI_API_KEY",  ""),
            openai_model    = os.environ.get("OPENAI_MODEL",    "gpt-4o"),
            github_token    = os.environ.get("GITHUB_TOKEN",    ""),
            github_username = os.environ.get("GITHUB_USERNAME", ""),
            docker_image    = os.environ.get("DOCKER_IMAGE",    "python:3.11-slim"),
            sandbox_timeout = int(os.environ.get("SANDBOX_TIMEOUT", "60")),
            max_retries     = int(os.environ.get("MAX_RETRIES",     "3")),
            workspace_dir   = os.environ.get("WORKSPACE_DIR",   "/tmp/ai-agent-workspace"),
        )


# Singleton
cfg = Config.from_env()
