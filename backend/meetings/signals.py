def circular_saved(sender, instance, **kwargs):
    from .services import circular_sent

    circular_sent(instance)
