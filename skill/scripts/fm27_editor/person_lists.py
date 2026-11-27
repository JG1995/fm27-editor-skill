"""The lists on people that can be written, in the shape that real files show.

The order of the parts and what an added item holds were read from files that the Editor saved,
where people's lists are changed thousands of times. Lists whose added item was never seen, such
as achievements and injuries, are not here.
"""

from collections.abc import Mapping

from fm27_editor.list_changes import ListShape
from fm27_editor.person_names import NO_DATE

PERSON_LISTS: Mapping[str, ListShape] = {
    "Plhs": ListShape(  # Playing History
        (
            *("year", "yror", "clid", "onln", "trib", "ytht", "apps", "gols"),
            *("cash", "divi", "info", "hsfl", "join", "leav"),
        ),
        empty={
            "year": NO_DATE.year,
            **{"yror": 0, "apps": 0, "gols": 0, "hsfl": 0},
            **{"join": NO_DATE, "leav": NO_DATE},
        },
        as_codes=frozenset({"apps", "gols"}),
    ),
    "Pdcn": ListShape(  # Days At Club/In Nation
        ("Ttea", "days", "0t21", "d152", "bfat", "etto", "0t19", "d021"), empty={"days": 1}
    ),
    "Phgc": ListShape(("hgty", "club"), empty={"hgty": 1}),  # Trained at club
    "Phgn": ListShape(("hgty", "nati"), empty={"hgty": 1}),  # Trained in nation
    "PNRs": ListShape(("ntin", "nati"), empty={"ntin": 80}),  # Second Nations
    "Pfvp": ListShape(("leve", "pers", "perm", "rrea"), empty={"leve": 100, "rrea": 1}),
    "Pfvc": ListShape(("leve", "club", "rrea"), empty={"leve": 100, "rrea": 1}),
    # The Editor works out the description from the proficiency, which real files change alone.
    # No file sets Cannot Speak Language.
    "PElg": ListShape(  # Additional Languages
        ("lang", "prof", "csln", "proe"),
        empty={"prof": 10, "proe": 2},
        kept=frozenset({"csln", "proe"}),
        needed=frozenset({"lang"}),
    ),
}
