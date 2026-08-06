"""Command-line entry points."""

from src.config import Config

Config.ensure_settings_file()
