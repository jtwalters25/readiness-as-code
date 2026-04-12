"""Verification plugins for the ready scan engine.

Adding a new verification method: drop a new `*_plugin.py` file in this
package that exports one or more classes inheriting from
`VerificationPlugin`. The engine auto-discovers them on startup — no
registration or engine changes required.
"""
