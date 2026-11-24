"""A mock ERP (the procurement system of record) served over MCP.

The store refuses any purchase order that lacks a valid approval token bound to
the exact requisition, whatever the caller claims.
"""
