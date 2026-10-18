from dataclasses import replace

import pytest

from tristhana.domain.catalog import (
    Asana,
    AsanaNames,
    Catalog,
    Meaning,
    Sequence,
    SequenceItem,
    SequenceKind,
    SequenceNames,
    SequenceStatus,
    groups,
    validate_catalog,
)

M = Meaning(en="meaning", ru="значение")


def _asana(slug: str, latin: str, ru: str, variants: tuple[str, ...] = ()) -> Asana:
    return Asana(slug, AsanaNames(latin=latin, iast=latin, ru=ru), M, variants)


def _block(slug: str, *items: SequenceItem) -> Sequence:
    return Sequence(
        slug=slug,
        kind=SequenceKind.BLOCK,
        status=SequenceStatus.CONFIRMED,
        names=SequenceNames(en=slug.title(), ru="Блок"),
        items=items,
    )


def _series(number: int, *items: SequenceItem, status: SequenceStatus | None = None) -> Sequence:
    return Sequence(
        slug=f"series-{number}",
        kind=SequenceKind.SERIES,
        status=status or (SequenceStatus.CONFIRMED if items else SequenceStatus.PLACEHOLDER),
        names=SequenceNames(en=f"Series {number}", ru="Серия"),
        items=items,
        number=number,
    )


def _valid() -> Catalog:
    asanas = (
        _asana("surya-namaskara", "Surya Namaskara", "Сурья Намаскар", ("a", "b")),
        _asana("parsvottanasana", "Parsvottanasana", "Паршвоттанасана"),
        _asana("marichyasana", "Marichyasana", "Маричиасана", ("a", "b")),
        _asana("drop-backs", "Drop-backs", "Прогибы назад"),
        _asana("urdhva-dhanurasana", "Urdhva Dhanurasana", "Урдхва Дханурасана"),
        _asana("padmasana", "Padmasana", "Падмасана"),
    )
    sequences = (
        _block(
            "opening", SequenceItem("surya-namaskara", "a"), SequenceItem("surya-namaskara", "b")
        ),
        _block("standing", SequenceItem("parsvottanasana", stop=True)),
        _block(
            "backbending",
            SequenceItem("urdhva-dhanurasana"),
            SequenceItem("drop-backs", optional=True, milestone=True),
        ),
        _block("finishing", SequenceItem("padmasana")),
        _series(
            1,
            SequenceItem("marichyasana", "a", stop=True),
            SequenceItem("marichyasana", "b", stop=True),
        ),
        *(_series(n) for n in range(2, 7)),
    )
    return Catalog(asanas=asanas, sequences=sequences)


def _with_sequence(catalog: Catalog, seq: Sequence) -> Catalog:
    return replace(
        catalog, sequences=tuple(seq if s.slug == seq.slug else s for s in catalog.sequences)
    )


def _messages(catalog: Catalog) -> str:
    return "\n".join(str(i) for i in validate_catalog(catalog))


def test_valid_catalog_has_no_issues() -> None:
    assert validate_catalog(_valid()) == []


def test_item_key() -> None:
    assert SequenceItem("marichyasana", "e").key == "marichyasana-e"
    assert SequenceItem("dandasana").key == "dandasana"


def test_rejects_bad_and_duplicate_slugs() -> None:
    cat = _valid()
    bad = replace(cat, asanas=(*cat.asanas, _asana("Bad_Slug", "Bad", "Плохо"), cat.asanas[1]))

    msg = _messages(bad)

    assert "Bad_Slug" in msg
    assert "duplicate asana slug 'parsvottanasana'" in msg


def test_rejects_variant_key_colliding_with_another_slug() -> None:
    cat = _valid()
    clash = replace(cat, asanas=(*cat.asanas, _asana("marichyasana-a", "Marichyasana A", "Маричи")))

    assert "collides" in _messages(clash)


def test_rejects_unknown_asana_and_variant() -> None:
    cat = _valid()
    seq = _series(1, SequenceItem("nope", stop=True), SequenceItem("marichyasana", "z", stop=True))

    msg = _messages(_with_sequence(cat, seq))

    assert "unknown asana 'nope'" in msg
    assert "unknown variant 'z'" in msg


def test_rejects_duplicate_item_in_sequence() -> None:
    seq = _series(
        1,
        SequenceItem("marichyasana", "a", stop=True),
        SequenceItem("marichyasana", "a", stop=True),
    )

    assert "appears twice" in _messages(_with_sequence(_valid(), seq))


def test_rejects_orphan_asana_and_variant() -> None:
    cat = _valid()
    orphan = replace(
        cat,
        asanas=(
            *cat.asanas[:2],
            _asana("marichyasana", "Marichyasana", "Маричиасана", ("a", "b", "c")),
            *cat.asanas[3:],
            _asana("kandasana", "Kandasana", "Кандасана"),
        ),
    )

    msg = _messages(orphan)

    assert "'kandasana' is not used" in msg
    assert "'marichyasana-c' is not used" in msg


def test_rejects_wrong_series_numbers_and_blocks() -> None:
    cat = _valid()
    broken = replace(
        cat, sequences=tuple(s for s in cat.sequences if s.slug not in {"series-6", "opening"})
    )

    msg = _messages(broken)

    assert "series numbers" in msg
    assert "blocks" in msg


def test_status_must_match_emptiness() -> None:
    cat = _valid()
    empty_confirmed = _series(2, status=SequenceStatus.CONFIRMED)
    filled_pending = _series(
        3, SequenceItem("marichyasana", "a", stop=True), status=SequenceStatus.PENDING
    )

    msg = _messages(_with_sequence(_with_sequence(cat, empty_confirmed), filled_pending))

    assert "series-2: confirmed series must have items" in msg
    assert "series-3: pending series must be empty" in msg


def test_series_must_end_on_a_stop_ignoring_optional_tail() -> None:
    cat = _valid()
    ends_open = _series(
        1, SequenceItem("marichyasana", "a", stop=True), SequenceItem("marichyasana", "b")
    )

    assert "must end on a stop point" in _messages(_with_sequence(cat, ends_open))


def test_optional_items_are_never_stops_and_milestones_must_be_optional() -> None:
    cat = _valid()
    seq = _block(
        "backbending",
        SequenceItem("urdhva-dhanurasana", milestone=True),
        SequenceItem("drop-backs", optional=True, stop=True),
    )

    msg = _messages(_with_sequence(cat, seq))

    assert "optional item cannot be a stop" in msg
    assert "milestone must be optional" in msg


def test_only_standing_block_has_a_stop_and_ends_with_it() -> None:
    cat = _valid()
    finishing = _block("finishing", SequenceItem("padmasana", stop=True))
    standing = _block("standing", SequenceItem("parsvottanasana"))

    msg = _messages(_with_sequence(_with_sequence(cat, finishing), standing))

    assert "finishing: blocks other than standing have no stop points" in msg
    assert "standing: must have exactly one stop point, on its last item" in msg


@pytest.mark.parametrize(
    ("names", "fragment"),
    [
        (AsanaNames(latin="Pāda", iast="Pāda", ru="Пада"), "latin"),
        (AsanaNames(latin="Pada", iast="Pada", ru="Pada"), "ru"),
        (AsanaNames(latin="Pada", iast="Pada", ru="Пёда"), "ru"),
        (AsanaNames(latin="Pada", iast="Paṁda", ru="Пада"), "iast"),
        (AsanaNames(latin=" Pada", iast="Pada", ru="Пада"), "latin"),
    ],
)
def test_name_charsets(names: AsanaNames, fragment: str) -> None:
    cat = _valid()
    first = replace(cat.asanas[1], names=names)
    bad = replace(cat, asanas=(cat.asanas[0], first, *cat.asanas[2:]))

    assert f"names.{fragment}" in _messages(bad)


def test_ru_meaning_must_be_cyrillic() -> None:
    cat = _valid()
    bad_asana = replace(cat.asanas[1], meaning=Meaning(en="x", ru="side stretch"))
    bad = replace(cat, asanas=(cat.asanas[0], bad_asana, *cat.asanas[2:]))

    assert "meaning.ru" in _messages(bad)


def test_groups_are_runs_of_the_same_asana() -> None:
    seq = _block(
        "opening",
        SequenceItem("surya-namaskara", "a"),
        SequenceItem("surya-namaskara", "b"),
        SequenceItem("padmasana"),
    )

    assert [[i.key for i in g] for g in groups(seq)] == [
        ["surya-namaskara-a", "surya-namaskara-b"],
        ["padmasana"],
    ]


def test_series_and_blocks_have_consistent_kind_fields() -> None:
    cat = _valid()
    block = replace(_block("finishing", SequenceItem("padmasana")), number=0)
    series = replace(_series(2), number=None)

    msg = _messages(_with_sequence(_with_sequence(cat, block), series))

    assert "finishing: blocks have no number or traditional name" in msg
    assert "series-2: series number must be 1-6, got None" in msg


def test_standing_needs_exactly_one_stop() -> None:
    standing = _block(
        "standing", SequenceItem("parsvottanasana", stop=True), SequenceItem("padmasana", stop=True)
    )

    assert "exactly one stop point" in _messages(_with_sequence(_valid(), standing))


def test_sequence_names_must_be_clean_text() -> None:
    seq = replace(
        _block(
            "opening", SequenceItem("surya-namaskara", "a"), SequenceItem("surya-namaskara", "b")
        ),
        names=SequenceNames(en="  ", ru="Блок\nБлок"),  # noqa: RUF001 - Cyrillic on purpose
    )

    msg = _messages(_with_sequence(_valid(), seq))

    assert "opening: names.en must be non-empty" in msg
    assert "opening: names.ru must be non-empty" in msg


def test_traditional_name_charsets_are_checked() -> None:
    seq = replace(
        _series(
            1,
            SequenceItem("marichyasana", "a", stop=True),
            SequenceItem("marichyasana", "b", stop=True),
        ),
        traditional_name=AsanaNames(latin="Yoga", iast="Yoga Ciṁ", ru="Йога"),
    )

    assert "traditional_name.iast" in _messages(_with_sequence(_valid(), seq))


def test_variant_codes_must_be_single_unique_letters() -> None:
    cat = _valid()
    bad = replace(cat.asanas[0], variants=("a", "b", "b", "-c"))

    msg = _messages(replace(cat, asanas=(bad, *cat.asanas[1:])))

    assert "duplicate variant 'b'" in msg
    assert "variant code '-c'" in msg


def test_duplicate_sequence_slug() -> None:
    cat = _valid()

    msg = _messages(replace(cat, sequences=(*cat.sequences, cat.sequences[0])))

    assert "duplicate sequence slug 'opening'" in msg
