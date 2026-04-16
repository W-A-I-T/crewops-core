from crewops_core import register_delivery_adapter, register_department, register_seed_entities


register_department("private-support", lambda request: f"private support layer handled: {request}")
register_seed_entities(
    {
        "entity_project_private_support": ("project", "Private Support", ["private support", "support"]),
    }
)
register_delivery_adapter("webhook", lambda payload: {"delivered": True, "payload": payload})
