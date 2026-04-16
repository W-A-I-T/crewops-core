from crewops_core import register_department


register_department(
    "operations",
    lambda request: f"operations example prepared next steps for: {request}",
)
