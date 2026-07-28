from wiki_kings.houses import assign_house_colors, normalize_house


def test_normalize_house_passes_through_plain_names():
    assert normalize_house("Windsor") == "Windsor"
    assert normalize_house("Tudor") == "Tudor"


def test_normalize_house_merges_plantagenet_angevin_variants():
    assert normalize_house("Plantagenet-Angevin") == "Plantagenet"
    assert normalize_house("Plantagenet–Angevin") == "Plantagenet"
    assert normalize_house("Plantagenet") == "Plantagenet"


def test_normalize_house_merges_saxe_coburg_windsor_transition():
    assert normalize_house("Saxe-Coburg and Gotha (by birth); Windsor (founder)") == "Windsor"
    assert normalize_house("Saxe-Coburg and Gotha (until 1917); Windsor (from 1917)") == "Windsor"
    assert normalize_house("Windsor (from 1917); Saxe-Coburg and Gotha (until 1917)") == "Windsor"


def test_normalize_house_leaves_plain_saxe_coburg_alone():
    # Edward VII reigned entirely before the 1917 rename -- no "Windsor" in his field.
    assert normalize_house("Saxe-Coburg and Gotha") == "Saxe-Coburg and Gotha"


def test_assign_house_colors_uses_validated_uk_table():
    colors = assign_house_colors(["Normandy", "Blois", "Normandy"])
    assert colors == {"Normandy": "#3987e5", "Blois": "#d95926"}


def test_assign_house_colors_falls_back_to_cycling_for_unknown_houses():
    colors = assign_house_colors(["Not A Real House", "Also Not Real"])
    assert colors["Not A Real House"] == "#3987e5"
    assert colors["Also Not Real"] == "#d95926"


def test_assign_house_colors_ignores_empty_house():
    assert assign_house_colors(["", "Normandy", ""]) == {"Normandy": "#3987e5"}
