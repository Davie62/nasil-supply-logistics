from django.db import models


class ActiveManager(models.Manager):
    """
    Returns only active, non-deleted records.
    """

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                is_deleted=False,
                is_active=True,
            )
        )


class AllObjectsManager(models.Manager):
    """
    Returns every record, including inactive and soft-deleted.
    """

    pass