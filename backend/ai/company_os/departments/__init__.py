"""
Company departments. Each module exposes NAME and run(db, today=None) -> list of
proposals, and acts only through kernel.propose. Order matters: the chief of
staff runs last so its brief covers what the others just did.
"""
from . import support, finance, customer_success, engineering, compliance, executive

DEPARTMENTS = [support, finance, customer_success, engineering, compliance, executive]
