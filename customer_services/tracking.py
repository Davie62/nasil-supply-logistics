from operations.models import DeliveryProof


def public_projection(shipment):
    """A deliberate whitelist, never a model/audit dump."""
    events = [{"label": "Shipment booked", "at": shipment.created_at}]
    labels = dict(shipment.STATUS_CHOICES)
    changes = shipment.history.filter(action="status_changed").exclude(from_status=shipment.status, to_status=shipment.status).order_by("created_at", "pk").values("from_status", "to_status", "created_at")
    for change in changes:
        if change["to_status"] in labels and change["to_status"] != change["from_status"]:
            events.append({"label": labels[change["to_status"]], "at": change["created_at"]})
    proof = DeliveryProof.objects.filter(shipment_id=shipment.pk).values("delivered_at", "recorded_at").first()
    return {"reference": shipment.tracking_number, "status": shipment.get_status_display(), "estimated_delivery": shipment.estimated_delivery,
            "events": events, "proof_confirmation": proof, "legacy_history": shipment.history.filter(action="legacy_snapshot").exists()}
