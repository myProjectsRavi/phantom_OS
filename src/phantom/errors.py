"""PHANTOM exception hierarchy."""

from __future__ import annotations


class PhantomError(Exception): ...


class PerceptionError(PhantomError): ...


class ActionError(PhantomError): ...


class RecipeError(PhantomError): ...


class SafetyError(PhantomError): ...


class IntentError(PhantomError): ...


class PlatformError(PhantomError): ...


class EmergencyStopError(PhantomError): ...
