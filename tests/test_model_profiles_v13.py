from src.locdex.model_profiles import DEFAULT_MODEL_KEY, get_model_profile


def test_qwen_is_default_supported_model():
    profile = get_model_profile(DEFAULT_MODEL_KEY)
    assert profile.key == "qwen"
    assert profile.status == "supported"
    assert profile.expected_sha256
    assert profile.approximate_size_gb > 15


def test_kimi_is_optional_experimental_model():
    profile = get_model_profile("kimi")
    assert profile.status == "experimental"
    assert profile.approximate_size_gb < 10
