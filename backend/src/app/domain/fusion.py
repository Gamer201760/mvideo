from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field

BASELINE = "baseline"
RANKER = "ranker"
DECISION = "decision_model"
TWIN = "catalog_twin"
SOURCES = (BASELINE, RANKER, DECISION, TWIN)
PRIMARIES = (RANKER, BASELINE, DECISION)
KNOWN = "known"
NEW = "new"
MODES = (KNOWN, NEW)
MIN_GOLD = 30


@dataclass(frozen=True, slots=True)
class Rule:
    primary: str
    twins: bool

    @property
    def name(self) -> str:
        return f"{self.primary}+twins" if self.twins else self.primary

    @classmethod
    def parse(cls, name: str) -> "Rule":
        primary, _, rest = name.partition("+")
        return cls(primary, rest == "twins")


RULES = tuple(Rule(p, t) for p in PRIMARIES for t in (False, True))

Options = Mapping[str, str | None]


def resolve(options: Options, rule: Rule) -> str | None:
    chosen: str | None = None
    if rule.primary == DECISION and DECISION in options:
        chosen = DECISION if options[DECISION] is not None else None
    elif rule.primary == BASELINE:
        chosen = BASELINE if options.get(BASELINE) is not None else None
    elif options.get(RANKER) is not None:
        chosen = RANKER
    if chosen is None and rule.twins and options.get(TWIN) is not None:
        chosen = TWIN
    return chosen


@dataclass(slots=True)
class Tally:
    gold: int = 0
    predicted: list[int] = field(default_factory=lambda: [0] * len(RULES))
    correct: list[int] = field(default_factory=lambda: [0] * len(RULES))

    def add(self, options: Options, truth: str) -> None:
        self.gold += 1
        for index, rule in enumerate(RULES):
            source = resolve(options, rule)
            if source is None:
                continue
            self.predicted[index] += 1
            self.correct[index] += 1 if options[source] == truth else 0

    def merge(self, other: "Tally") -> None:
        self.gold += other.gold
        for index in range(len(RULES)):
            self.predicted[index] += other.predicted[index]
            self.correct[index] += other.correct[index]

    def f1(self, index: int) -> float:
        denominator = self.predicted[index] + self.gold
        return 2 * self.correct[index] / denominator if denominator else 0.0

    def best(self) -> Rule:
        index = max(range(len(RULES)), key=lambda i: (round(self.f1(i), 6), -i))
        return RULES[index]


@dataclass(slots=True)
class RuleBook:
    tallies: dict[tuple[str, str], Tally] = field(default_factory=lambda: defaultdict(Tally))

    def add(self, attribute: str, mode: str, options: Options, truth: str) -> None:
        self.tallies[(attribute, mode)].add(options, truth)

    def mode_tally(self, mode: str) -> Tally:
        total = Tally()
        for (_, tally_mode), tally in self.tallies.items():
            if tally_mode == mode:
                total.merge(tally)
        return total

    def choose(self, min_gold: int = MIN_GOLD) -> "FusionRules":
        defaults = {mode: self.mode_tally(mode).best() for mode in MODES}
        specific = {key: t.best() for key, t in self.tallies.items()
                    if t.gold >= min_gold and t.best() != defaults[key[1]]}
        return FusionRules(defaults, specific)


@dataclass(frozen=True, slots=True)
class FusionRules:
    defaults: Mapping[str, Rule]
    specific: Mapping[tuple[str, str], Rule]

    def rule(self, attribute: str, mode: str) -> Rule:
        return self.specific.get((attribute, mode), self.defaults[mode])

    def to_json(self) -> dict[str, object]:
        return {
            "defaults": {mode: rule.name for mode, rule in self.defaults.items()},
            "specific": [{"attribute": a, "mode": m, "rule": r.name}
                         for (a, m), r in sorted(self.specific.items())],
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, object]) -> "FusionRules":
        defaults_raw = raw["defaults"]
        specific_raw = raw["specific"]
        assert isinstance(defaults_raw, Mapping) and isinstance(specific_raw, list)
        defaults = {str(m): Rule.parse(str(r)) for m, r in defaults_raw.items()}
        specific = {(str(i["attribute"]), str(i["mode"])): Rule.parse(str(i["rule"]))
                    for i in specific_raw}
        return cls(defaults, specific)
