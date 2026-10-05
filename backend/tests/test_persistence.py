from app.persistence import mask_sensitive


def test_sensitive_data_is_masked_in_summaries():
    value = (
        "CPF 123.456.789-09; email pessoa@example.com; telefone (11) 99999-8888; cartão 4111 1111 1111 1111"
    )
    masked = mask_sensitive(value)
    assert masked.count("[MASCARADO]") >= 4
    assert "123.456.789-09" not in masked
    assert "pessoa@example.com" not in masked
    assert "99999-8888" not in masked
    assert "4111 1111 1111 1111" not in masked
