from httpxgen.generator.naming import (
    class_name,
    enum_member,
    identifier,
    string_literal,
    used_names,
)


def test_class_name_normalizes_words_and_leading_digits():
    assert class_name("payment_method") == "PaymentMethod"
    assert class_name("HTTPResponse") == "HTTPResponse"
    assert class_name("3d-secure") == "Model3DSecure"
    assert class_name("") == "Model"


def test_identifier_normalizes_camel_case_keywords_and_leading_digits():
    assert identifier("listCharges") == "list_charges"
    assert identifier("page-size") == "page_size"
    assert identifier("class") == "class_"
    assert identifier("3dSecure") == "value_3d_secure"


def test_enum_member_produces_a_valid_constant_name():
    assert enum_member("bank-transfer") == "BANK_TRANSFER"
    assert enum_member("3d-secure") == "VALUE_3D_SECURE"
    assert enum_member("") == "EMPTY"


def test_string_literal_uses_json_escaping_without_ascii_substitution():
    assert string_literal('Grüße "Welt"') == '"Grüße \\"Welt\\""'


def test_used_names_matches_whole_identifiers_in_candidate_order():
    assert used_names("list[datetime] | Any", ("date", "datetime", "Any")) == [
        "datetime",
        "Any",
    ]
