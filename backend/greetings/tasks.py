from celery import shared_task


@shared_task
def hourly() -> int:
    """Entwürfe vorbereiten und fällige Glückwünsche versenden (alle Vereine)."""
    from django.utils import timezone

    from core.tenancy import org_context, rls_bypass

    from .models import GreetingSettings
    from .services import prepare, send_due

    with rls_bypass():
        orgs = [
            s.organization
            for s in GreetingSettings.objects.select_related("organization").filter(
                organization__is_active=True
            )
        ]
    now = timezone.now()
    sent = 0
    for org in orgs:
        with org_context(org):
            prepare(org, timezone.localtime(now).date())
            sent += send_due(org, now)
    return sent
