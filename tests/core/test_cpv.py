from uvo_core.domain.cpv import cpv_label_sk, cpv_prefix, load_cpv_labels


def test_cpv_prefix_normalises():
    assert cpv_prefix("72000000-5") == "72000000"
    assert cpv_prefix("72 000 000") == "72000000"
    assert cpv_prefix("72") == "72000000"
    assert cpv_prefix(None) == "00000000"


def test_labels_load_and_are_cached():
    labels = load_cpv_labels()
    assert labels and load_cpv_labels() is labels


def test_label_falls_back_to_code():
    assert cpv_label_sk("12345670") == "12345670"
