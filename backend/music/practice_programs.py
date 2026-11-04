"""Die Serienvorlage gilt, bis ein Einzeltermin ein eigenes Programm erhält."""


def with_programs(queryset):
    return queryset.prefetch_related(
        "items__arrangement__piece", "programs__items__arrangement__piece"
    )


def content(source):
    return {
        "focus": source.focus,
        "items": [
            {
                "arrangement": item.arrangement_id,
                "title": item.arrangement.piece.title,
                "focus": item.focus,
            }
            for item in sorted(
                source.items.all(), key=lambda i: (getattr(i, "position", i.pk), i.pk)
            )
        ],
    }


def program_for(rehearsal, original_start):
    override = next(
        (p for p in rehearsal.programs.all() if p.original_start == original_start), None
    )
    return {
        **content(override if override is not None else rehearsal),
        "overridden": override is not None,
    }
