from pathlib import Path


def test_tx_and_rx_protocol_models_are_identical():
    rx_models = Path(__file__).resolve().parents[1] / "gaussianobject_rx" / "protocol" / "models.py"
    tx_models = Path(__file__).resolve().parents[2] / "Tx" / "gaussianobject_tx" / "protocol" / "models.py"
    assert rx_models.read_bytes() == tx_models.read_bytes()
