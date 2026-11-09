"""Endgültige Mitgliederergebnisse; Mittelwerte nur bei gleichen Bedingungen.

Werte bleiben bis zur Ausgabe Decimal. Teilnahmen zählen Personen je Wettbewerb,
Platzierungen je Einzelwertung. Gäste bleiben im Starterfeld für die Rangberechnung.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from django.utils.translation import gettext

from . import ranking, services
from .models import AwardGrant, Competition, Placing, Prize, Score, Scoring, ShootOff, Starter


def _number(value):
    return float(value) if value is not None else None


def _mean(values):
    return sum(values, Decimal(0)) / len(values) if values else None


def _conditions(scoring):
    comp = scoring.competition
    program = scoring.program
    config = {
        "discipline": comp.discipline.strip().casefold(),
        "details": sorted(
            (str(d.get("label", "")).strip().casefold(), str(d.get("value", "")).strip().casefold())
            for d in comp.details
            if isinstance(d, dict)
        ),
        "name": scoring.name.strip().casefold(),
        "method": scoring.method,
        "target": scoring.target,
        "custom_target": scoring.custom_target if scoring.target == "eigen" else {},
        "shots": scoring.shots,
        "counted": scoring.counted_shots or scoring.shots,
        "unit": scoring.unit_label.strip().casefold(),
        "decimals": scoring.decimals,
        "maximum": str(scoring.max_per_shot),
        "higher_better": scoring.higher_better,
    }
    if program and (program.position.strip() or program.distance is not None):
        config["position"] = program.position.strip().casefold()
        config["distance"] = program.distance
    # Ohne bekannte Disziplin oder Scheibe beweist eine gleiche Bezeichnung nichts.
    if not scoring.target and not comp.discipline.strip():
        config["competition"] = comp.pk
    key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:24]
    target = services.target_of(scoring)
    parts = [comp.discipline or (target.name if target else comp.title), scoring.name]
    if target and target.name.casefold() != (comp.discipline or "").casefold():
        parts.append(target.name)
    if program and program.position.strip():
        parts.append(program.position.strip())
    if program and program.distance is not None:
        parts.append(f"{program.distance} m")
    if scoring.shots:
        parts.append(gettext("%(n)s Schuss") % {"n": scoring.shots})
    if scoring.counted_shots and scoring.counted_shots != scoring.shots:
        parts.append(gettext("beste %(n)s gewertet") % {"n": scoring.counted_shots})
    parts.append(scoring.unit_label)
    if scoring.method != Scoring.Method.FREE and scoring.get_method_display() != scoring.unit_label:
        parts.append(scoring.get_method_display())
    parts.extend(str(d.get("value", "")) for d in comp.details if isinstance(d, dict))
    return key, {
        "id": key,
        "label": " · ".join(p for p in parts if p),
        "unit_label": scoring.unit_label,
        "method": scoring.method,
        "higher_better": scoring.higher_better,
        "counted_shots": scoring.counted_shots or scoring.shots,
        "maximum": _number(scoring.max_value),
        "is_rings": scoring.method in (Scoring.Method.RINGS, Scoring.Method.DECIMAL)
        or (
            scoring.method == Scoring.Method.FREE
            and scoring.higher_better
            and scoring.unit_label.strip().casefold() == "ringe"
        ),
    }


def _load(org, person_id=None):
    """Ranglisten wiederverwenden, Daten gebündelt laden; keine Abfrage je Mitglied."""
    competitions = Competition.objects.filter(organization=org, status=Competition.Status.FINAL)
    if person_id is not None:
        competitions = competitions.filter(starters__membership__person_id=person_id).distinct()
    starters = list(
        Starter.objects.filter(organization=org, competition__in=competitions)
        .select_related("competition", "membership", "unit")
        .order_by("competition__date", "pk")
    )
    by_comp = defaultdict(list)
    for st in starters:
        by_comp[st.competition_id].append(st)
    scorings = list(
        Scoring.objects.filter(
            organization=org, competition__in=competitions, kind=Scoring.Kind.INDIVIDUAL
        ).select_related("competition", "program")
    )
    scores = defaultdict(dict)
    for sc_id, st_id, value in Score.objects.filter(
        organization=org, scoring__in=scorings
    ).values_list("scoring_id", "starter_id", "value"):
        scores[sc_id][st_id] = value
    placings = defaultdict(dict)
    for p in Placing.objects.filter(organization=org, scoring__in=scorings, starter__isnull=False):
        placings[p.scoring_id][p.starter_id] = p
    shootoffs = defaultdict(list)
    for so in ShootOff.objects.filter(organization=org, scoring__in=scorings).prefetch_related(
        "entries"
    ):
        shootoffs[so.scoring_id].append((so.number, {e.key: e.value for e in so.entries.all()}))
    prizes = defaultdict(list)
    for p in Prize.objects.filter(
        organization=org, competition__in=competitions, winner__isnull=False
    ):
        prizes[p.winner_id].append(p.name)

    def eligible(st):
        return (
            st.membership_id is not None
            and st.membership.organization_id == org.pk
            and st.membership.purged_at is None
            and not st.out_of_competition
            and st.presence != "fehlt"
            and (person_id is None or st.membership.person_id == person_id)
        )

    def not_counted(st):
        """Warum ein Start nicht zählt (für den Hinweis neben den Teilnahmen)."""
        if (
            st.membership_id is None
            or st.membership.organization_id != org.pk
            or st.membership.purged_at is not None
        ):
            return "guests"
        if st.out_of_competition:
            return "out_of_competition"
        if st.presence == "fehlt":
            return "absent"
        return None

    starts = []
    members = {}
    skipped = []
    for st in starters:
        if not eligible(st):
            reason = not_counted(st) if person_id is None else None
            if reason:
                skipped.append(
                    {
                        "reason": reason,
                        "competition": st.competition_id,
                        "date": st.competition.date.isoformat(),
                        "form": st.competition.form,
                    }
                )
            continue
        pid = st.membership.person_id
        members[pid] = {"membership": st.membership_id, "name": st.name}
        starts.append(
            {
                "person": pid,
                "membership": st.membership_id,
                "name": st.name,
                "competition": st.competition_id,
                "title": st.competition.title,
                "date": st.competition.date.isoformat(),
                "form": st.competition.form,
                "own": st.competition.own,
                "unit_name": st.unit.name if st.unit_id else "",
                "prizes": prizes[st.pk],
                "starter": st.pk,
            }
        )
    start_map = {s["starter"]: s for s in starts}
    groups = {}
    results = []
    for sc in scorings:
        comp_starters = by_comp[sc.competition_id]
        if not any(st.pk in start_map for st in comp_starters):
            continue
        key, group = _conditions(sc)
        groups[key] = group
        if sc.competition.own:
            values = scores[sc.pk]
            tb = services._tiebreaks(sc, comp_starters)
            ranked = ranking.rank(
                [
                    ranking.Entry(
                        f"s{st.pk}", values.get(st.pk), st.out_of_competition, tb.get(st.pk, ())
                    )
                    for st in comp_starters
                ],
                higher_better=sc.higher_better,
                prize_places=sc.prize_places,
                shootoffs=shootoffs[sc.pk],
            )
            places = {int(p.key[1:]): p.place for p in ranked.placed}
            field = len(ranked.placed)
        else:
            values = {st_id: p.value for st_id, p in placings[sc.pk].items()}
            places = {st_id: p.place for st_id, p in placings[sc.pk].items()}
            # Bei fremden Wettbewerben ist nur die ausdrücklich erfasste Feldgröße bekannt.
            field = sc.field_size
        for st in comp_starters:
            if st.pk not in start_map:
                continue
            results.append(
                {
                    **start_map[st.pk],
                    "scoring": sc.name,
                    "scoring_id": sc.pk,
                    "group": key,
                    "value": values.get(st.pk),
                    "place": places.get(st.pk),
                    "field": field,
                    "prize_place": bool(places.get(st.pk) and places[st.pk] <= sc.prize_places),
                    "unit_label": sc.unit_label,
                }
            )
    return starts, results, groups, members, skipped


def _performance(rows, group):
    valid = [r for r in rows if r["value"] is not None]
    by_person = defaultdict(list)
    for r in valid:
        by_person[r["person"]].append(r["value"])
    values = [r["value"] for r in valid]
    best = (max if group["higher_better"] else min)(values) if values else None
    average = _mean(values)
    counted = group["counted_shots"]
    return {
        "count": len(values),
        "average": _number(average),
        "member_average": _number(_mean([_mean(v) for v in by_person.values()])),
        "per_shot": _number(average / counted)
        if average is not None and counted and group["is_rings"]
        else None,
        "best": _number(best),
        "best_names": sorted({r["name"] for r in valid if r["value"] == best}),
    }


def competition_statistics(org, *, person_id=None, year=None, form="", group_id=""):
    starts, results, groups, members, skipped = _load(org, person_id)
    if form:
        starts = [s for s in starts if s["form"] == form]
        results = [r for r in results if r["form"] == form]
    available_groups = {r["group"] for r in results}
    options = sorted(
        (g for k, g in groups.items() if k in available_groups), key=lambda g: g["label"]
    )
    years = sorted({int(s["date"][:4]) for s in starts}, reverse=True)
    if group_id:
        results = [r for r in results if r["group"] == group_id]
        keys = {(r["person"], r["competition"]) for r in results}
        starts = [s for s in starts if (s["person"], s["competition"]) in keys]
    # Nicht gezählte Starts nur aus den Wettbewerben, die auch die Auswertung enthält.
    shown = {s["competition"] for s in starts} | {r["competition"] for r in results}
    skipped = [s for s in skipped if s["competition"] in shown]
    if year is not None:
        skipped = [s for s in skipped if int(s["date"][:4]) == year]
    all_results = list(
        {(r["person"], r["competition"], r["scoring_id"]): r for r in results}.values()
    )
    results = all_results
    if year is not None:
        starts = [s for s in starts if int(s["date"][:4]) == year]
        results = [r for r in results if int(r["date"][:4]) == year]
    # Auch nach Wiedereintritt oder mehreren Mitgliedschaften zählt die Person nur einmal.
    starts = list({(s["person"], s["competition"]): s for s in starts}.values())
    results = list({(r["person"], r["competition"], r["scoring_id"]): r for r in results}.values())
    current_groups = {r["group"] for r in results if r["value"] is not None}
    selected = (
        groups.get(group_id)
        if group_id
        else (groups[next(iter(current_groups))] if len(current_groups) == 1 else None)
    )
    performance = _performance(results, selected) if selected else None
    if performance is not None:
        valid = [r for r in all_results if r["group"] == selected["id"] and r["value"] is not None]
        previous_year = (
            year if year is not None else max((int(r["date"][:4]) for r in valid), default=0)
        ) - 1
        previous = _mean([r["value"] for r in valid if int(r["date"][:4]) == previous_year])
        current = _mean([r["value"] for r in valid if int(r["date"][:4]) == previous_year + 1])
        performance.update(
            previous_year=previous_year,
            previous_average=_number(previous),
            change=_number(current - previous)
            if current is not None and previous is not None
            else None,
        )
    per_group = []
    for g in options:
        rs = [r for r in results if r["group"] == g["id"]]
        if rs:
            per_group.append({**g, **_performance(rs, g)})
    by_member = []
    for pid in sorted({s["person"] for s in starts}, key=lambda p: members[p]["name"].casefold()):
        rs = [r for r in results if r["person"] == pid]
        ss = [s for s in starts if s["person"] == pid]
        p = _performance(rs, selected) if selected else None
        by_member.append(
            {
                **members[pid],
                "starts": len(ss),
                "wins": sum(r["place"] == 1 for r in rs),
                "podiums": sum(r["place"] is not None and r["place"] <= 3 for r in rs),
                "prizes": sum(len(s["prizes"]) for s in ss),
                "count": p["count"] if p else 0,
                "average": p["average"] if p else None,
                "best": p["best"] if p else None,
            }
        )
    buckets = []
    for y in sorted({int(s["date"][:4]) for s in starts}):
        ss = [s for s in starts if int(s["date"][:4]) == y]
        rs = [r for r in results if int(r["date"][:4]) == y]
        p = _performance(rs, selected) if selected else None
        buckets.append(
            {
                "year": y,
                "starts": len(ss),
                "members": len({s["person"] for s in ss}),
                "count": p["count"] if p else 0,
                "average": p["average"] if p else None,
            }
        )
    awards = AwardGrant.objects.filter(
        organization=org,
        membership__organization=org,
        membership__purged_at__isnull=True,
        dignity_state__in=("", AwardGrant.DignityState.CONFIRMED),
    ).filter(Q(competition__status=Competition.Status.FINAL) | Q(competition=None, manual=True))
    if person_id is not None:
        awards = awards.filter(membership__person_id=person_id)
    if form:
        awards = awards.filter(competition__form=form)
    if group_id:
        awards = awards.filter(award__scoring_id__in={r["scoring_id"] for r in all_results})
    years = sorted(set(years) | set(awards.values_list("year", flat=True)), reverse=True)
    if year is not None:
        awards = awards.filter(year=year)
    award_rows = [
        {
            "id": a.pk,
            "year": a.year,
            "name": a.name,
            "title": a.full_title or (a.trophy.name if a.trophy_id else a.item),
            "competition": a.competition_id,
            "competition_title": a.competition.title if a.competition_id else "",
        }
        for a in awards.select_related("competition", "trophy").order_by("-year", "-pk")
    ]
    public_results = []
    for r in results:
        public_results.append(
            {
                k: _number(v) if k == "value" else v
                for k, v in r.items()
                if k not in ("person", "starter", "prizes")
            }
        )
    for s in starts:
        if s["form"] == Competition.Form.BIRD:
            public_results.append({k: v for k, v in s.items() if k not in ("person", "starter")})
    return {
        "years": years,
        "groups": options,
        "selected_group": selected,
        "summary": {
            "competitions": len({s["competition"] for s in starts}),
            "members": len(by_member),
            "starts": len(starts),
            "wins": sum(m["wins"] for m in by_member),
            "podiums": sum(m["podiums"] for m in by_member),
            "prizes": sum(m["prizes"] for m in by_member),
            "awards": len(award_rows),
            "not_counted": {
                k: sum(s["reason"] == k for s in skipped)
                for k in ("guests", "out_of_competition", "absent")
            },
        },
        "performance": performance,
        "group_summary": per_group,
        "buckets": buckets,
        "members": by_member,
        "results": sorted(public_results, key=lambda r: r["date"], reverse=True),
        "awards": award_rows,
    }
