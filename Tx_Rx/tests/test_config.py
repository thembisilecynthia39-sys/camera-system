from pathlib import Path

import pytest

from tx_rx.config import TxRxConfigError, load_config


def test_load_config_returns_fixed_absolute_staging_root(tmp_path):
    config_path = tmp_path / "config.yaml"
    staging_root = tmp_path / "visible-staging"
    config_path.write_text(
        f'schema_version: "1.0"\nstaging_root: {staging_root}\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.staging_root == staging_root


def test_relative_staging_root_is_rejected(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        'schema_version: "1.0"\nstaging_root: relative/staging\n',
        encoding="utf-8",
    )

    with pytest.raises(TxRxConfigError, match="staging_root must be an absolute path"):
        load_config(config_path)
