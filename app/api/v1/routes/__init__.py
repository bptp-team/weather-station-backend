"""One module per resource (e.g. readings.py, stations.py, health.py).

Routes only translate HTTP <-> use case: they validate input with the schemas,
delegate to app/services and return the response schema. No business rules here.
"""
