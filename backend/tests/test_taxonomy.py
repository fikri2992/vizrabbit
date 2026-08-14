from app.domain.taxonomy import BUILT_IN_CATEGORIES, Category, Severity, requires_project_rule


def test_category_values_are_stable_wire_strings():
    assert {c.value for c in Category} == {"anatomy", "physics", "artifact", "brand", "memory"}


def test_severity_values_are_stable_wire_strings():
    assert {s.value for s in Severity} == {"blocker", "warning", "nitpick"}


def test_built_in_categories_need_no_project_rule():
    for category in BUILT_IN_CATEGORIES:
        assert requires_project_rule(category) is False


def test_brand_and_memory_require_a_project_rule():
    assert requires_project_rule(Category.BRAND) is True
    assert requires_project_rule(Category.MEMORY) is True


def test_every_category_is_classified():
    """No category may be left out of the built-in / project-rule split."""
    for category in Category:
        assert isinstance(requires_project_rule(category), bool)
