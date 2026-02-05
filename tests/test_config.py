"""
Unit tests for the Config module.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from scraper.config import Config, DEFAULTS, _deep_merge, get_config, reset_config

# Ensure Path is available for assertions
Path = Path


class TestDeepMerge:
    """Tests for the _deep_merge helper function."""

    def test_merge_flat_dicts(self):
        """Merging flat dicts should override values."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested_dicts(self):
        """Nested dicts should be merged recursively."""
        base = {"outer": {"a": 1, "b": 2}}
        override = {"outer": {"b": 3, "c": 4}}
        result = _deep_merge(base, override)
        assert result == {"outer": {"a": 1, "b": 3, "c": 4}}

    def test_merge_does_not_mutate_base(self):
        """Base dict should not be mutated."""
        base = {"a": 1}
        override = {"b": 2}
        _deep_merge(base, override)
        assert base == {"a": 1}


class TestConfigDefaults:
    """Tests for default configuration values."""

    def setup_method(self):
        """Reset config before each test."""
        Config.reset()

    def teardown_method(self):
        """Reset config after each test."""
        Config.reset()

    def test_defaults_loaded_when_no_file(self):
        """Config should use DEFAULTS when no config file exists."""
        # Create config pointing to non-existent file
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.get("urls.base_url") == DEFAULTS["urls"]["base_url"]
        assert config.get("http.timeout") == DEFAULTS["http"]["timeout"]
        assert config.get("delays.min_delay") == DEFAULTS["delays"]["min_delay"]

    def test_all_default_sections_present(self):
        """All default sections should be accessible."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.urls is not None
        assert config.http is not None
        assert config.delays is not None
        assert config.retry is not None
        assert config.concurrency is not None
        assert config.paths is not None
        assert config.logging is not None


class TestConfigNestedAccess:
    """Tests for nested access via dot notation."""

    def setup_method(self):
        Config.reset()

    def teardown_method(self):
        Config.reset()

    def test_get_nested_value(self):
        """Should retrieve nested values using dot notation."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.get("urls.base_url") == "https://jamabandi.nic.in"
        assert config.get("http.user_agent").startswith("Mozilla")
        assert config.get("concurrency.max_workers") == 8

    def test_get_deeply_nested(self):
        """Should handle multiple levels of nesting."""
        config = Config(config_path="/nonexistent/config.yaml")

        # Access section directly
        assert config.get("urls") == DEFAULTS["urls"]

    def test_missing_key_returns_default(self):
        """Missing keys should return the provided default."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.get("nonexistent.key") is None
        assert config.get("nonexistent.key", "fallback") == "fallback"
        assert config.get("urls.nonexistent", 42) == 42

    def test_missing_intermediate_key(self):
        """Missing intermediate keys should return default."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.get("foo.bar.baz", "default") == "default"


class TestConfigPropertyAccess:
    """Tests for property-based section access."""

    def setup_method(self):
        Config.reset()

    def teardown_method(self):
        Config.reset()

    def test_urls_property(self):
        """urls property should return urls section."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.urls["base_url"] == "https://jamabandi.nic.in"
        assert config.urls["form_path"] == "/PublicNakal/CreateNewRequest"

    def test_http_property(self):
        """http property should return http section."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.http["timeout"] == 30
        assert config.http["verify_ssl"] is False

    def test_delays_property(self):
        """delays property should return delays section."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.delays["min_delay"] == 1.0
        assert config.delays["max_delay"] == 2.5

    def test_retry_property(self):
        """retry property should return retry section."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.retry["max_retries"] == 3
        assert config.retry["retry_delay"] == 5.0

    def test_concurrency_property(self):
        """concurrency property should return concurrency section."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.concurrency["max_workers"] == 8
        assert config.concurrency["default_workers"] == 3

    def test_paths_property(self):
        """paths property should return paths section."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.paths["downloads_dir"] == "downloads"
        assert config.paths["logs_dir"] == "logs"

    def test_logging_property(self):
        """logging property should return logging section."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.logging["level"] == "INFO"
        assert config.logging["max_file_size_mb"] == 10


class TestConfigSingleton:
    """Tests for singleton pattern."""

    def setup_method(self):
        Config.reset()

    def teardown_method(self):
        Config.reset()

    def test_same_instance_returned(self):
        """Multiple calls should return the same instance."""
        config1 = Config(config_path="/nonexistent/config.yaml")
        config2 = Config()

        assert config1 is config2

    def test_singleton_preserves_state(self):
        """Singleton should preserve loaded configuration."""
        config1 = Config(config_path="/nonexistent/config.yaml")
        original_value = config1.get("http.timeout")

        config2 = Config()
        assert config2.get("http.timeout") == original_value


class TestConfigReset:
    """Tests for Config.reset() functionality."""

    def setup_method(self):
        Config.reset()

    def teardown_method(self):
        Config.reset()

    def test_reset_allows_fresh_instance(self):
        """reset() should allow creating a fresh instance."""
        config1 = Config(config_path="/nonexistent/config.yaml")
        id1 = id(config1)

        Config.reset()

        config2 = Config(config_path="/nonexistent/config.yaml")
        id2 = id(config2)

        assert id1 != id2

    def test_reset_clears_initialization_flag(self):
        """reset() should clear the initialization flag."""
        Config(config_path="/nonexistent/config.yaml")
        assert Config._initialized is True

        Config.reset()

        assert Config._initialized is False
        assert Config._instance is None


class TestConfigYamlLoading:
    """Tests for YAML file loading."""

    def setup_method(self):
        Config.reset()

    def teardown_method(self):
        Config.reset()

    def test_load_from_yaml_file(self):
        """Should load configuration from YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"http": {"timeout": 60}}, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            assert config.get("http.timeout") == 60
        finally:
            os.unlink(temp_path)

    def test_yaml_merged_over_defaults(self):
        """YAML values should override defaults, preserving unspecified."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"http": {"timeout": 99}}, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            # Overridden value
            assert config.get("http.timeout") == 99
            # Default value preserved
            assert config.get("http.verify_ssl") is False
            # Other sections untouched
            assert config.get("urls.base_url") == DEFAULTS["urls"]["base_url"]
        finally:
            os.unlink(temp_path)

    def test_empty_yaml_uses_defaults(self):
        """Empty YAML file should use all defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            assert config.get("http.timeout") == DEFAULTS["http"]["timeout"]
        finally:
            os.unlink(temp_path)


class TestConfigReload:
    """Tests for config reload functionality."""

    def setup_method(self):
        Config.reset()

    def teardown_method(self):
        Config.reset()

    def test_reload_updates_values(self):
        """reload() should update configuration values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"http": {"timeout": 10}}, f)
            temp_path = f.name

        try:
            config = Config(config_path=temp_path)
            assert config.get("http.timeout") == 10

            # Update the file
            with open(temp_path, "w") as f:
                yaml.dump({"http": {"timeout": 99}}, f)

            config.reload()
            assert config.get("http.timeout") == 99
        finally:
            os.unlink(temp_path)

    def test_reload_with_new_path(self):
        """reload() with new path should load from new file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f1:
            yaml.dump({"http": {"timeout": 10}}, f1)
            temp_path1 = f1.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f2:
            yaml.dump({"http": {"timeout": 99}}, f2)
            temp_path2 = f2.name

        try:
            config = Config(config_path=temp_path1)
            assert config.get("http.timeout") == 10

            config.reload(config_path=temp_path2)
            assert config.get("http.timeout") == 99
        finally:
            os.unlink(temp_path1)
            os.unlink(temp_path2)


class TestBackwardCompatibility:
    """Tests for backward compatibility with logger module."""

    def setup_method(self):
        Config.reset()

    def teardown_method(self):
        Config.reset()

    def test_get_config_returns_singleton(self):
        """get_config() should return Config singleton."""
        config1 = get_config()
        config2 = Config()

        assert config1 is config2

    def test_reset_config_clears_singleton(self):
        """reset_config() should clear the singleton."""
        config1 = get_config()
        reset_config()
        config2 = get_config()

        assert config1 is not config2

    def test_attribute_access_on_paths(self):
        """paths section should support attribute-style access."""
        config = Config(config_path="/nonexistent/config.yaml")

        # This is how logger.py accesses config
        assert config.paths.logs_dir == Path("logs")
        assert config.paths.downloads_dir == Path("downloads")

    def test_attribute_access_on_logging(self):
        """logging section should support attribute-style access."""
        config = Config(config_path="/nonexistent/config.yaml")

        # This is how logger.py accesses config
        assert config.logging.level == "INFO"
        assert config.logging.max_file_size_mb == 10
        assert config.logging.backup_count == 5

    def test_attribute_access_on_http(self):
        """http section should support attribute-style access."""
        config = Config(config_path="/nonexistent/config.yaml")

        assert config.http.timeout == 30
        assert config.http.verify_ssl is False

    def test_section_proxy_dict_access(self):
        """Section proxy should support both dict and attribute access."""
        config = Config(config_path="/nonexistent/config.yaml")

        # Dict-style
        assert config.urls["base_url"] == "https://jamabandi.nic.in"
        # Attribute-style
        assert config.urls.base_url == "https://jamabandi.nic.in"
