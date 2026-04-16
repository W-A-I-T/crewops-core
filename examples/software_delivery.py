from crewops_core import register_department


register_department(
    "software",
    lambda request: f"software delivery example drafted a response for: {request}",
)
