"""
Central config — reads from environment / .env file.
"""
import os
import tempfile
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# Default workspace under the system temp directory (works on Windows + Linux)
_DEFAULT_WORKSPACE = os.path.join(tempfile.gettempdir(), "issuepilot-workspace")


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
    workspace_dir:   str = field(default_factory=lambda: _DEFAULT_WORKSPACE)

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
            workspace_dir   = os.environ.get("WORKSPACE_DIR",   _DEFAULT_WORKSPACE),
        )


# Singleton
cfg = Config.from_env()
