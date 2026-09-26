"""Persistent domain models will be introduced with M1/M4.

M0 deliberately keeps schema creation out of the bootstrap layer. Database models and
migrations are added only when a module has a concrete persistence requirement.
"""
