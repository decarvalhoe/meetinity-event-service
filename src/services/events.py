"""Service layer for event orchestration and validation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.repositories.events import EventRepository

__all__ = [
    "EventNotFoundError",
    "EventService",
    "ValidationError",
]


class ValidationError(Exception):
    """Raised when incoming payload validation fails."""

    def __init__(self, errors: Dict[str, List[str]], message: str = "Validation échouée."):
        super().__init__(message)
        self.errors = errors
        self.message = message


class EventNotFoundError(Exception):
    """Raised when an event could not be located."""


class EventService:
    """High level operations for managing events."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = EventRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_events(
        self,
        *,
        event_type: Optional[str] = None,
        location: Optional[str] = None,
        before: Optional[str] = None,
        after: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        cleaned_type = self._normalize_filter_value(event_type)
        cleaned_location = self._normalize_filter_value(location)
        before_value = self._normalize_filter_value(before)
        after_value = self._normalize_filter_value(after)

        before_date = self._parse_filter_date(before_value, "before")
        after_date = self._parse_filter_date(after_value, "after")

        events = self.repository.list_events(
            event_type=cleaned_type,
            location=cleaned_location,
            before=before_date,
            after=after_date,
        )
        return [self._serialize_event(event) for event in events]

    def get_event(self, event_id: int) -> Dict[str, Any]:
        try:
            event = self.repository.get_event(event_id)
        except LookupError as exc:
            raise EventNotFoundError(str(exc)) from exc
        return self._serialize_event(event)

    def create_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        clean_payload = self._validate_event_payload(payload, require_title=True)

        event_date = clean_payload.pop("event_date", date.today())
        series = None
        series_name = clean_payload.pop("series_name", None)
        series_id = clean_payload.pop("series_id", None)
        if series_id is not None:
            series = self.repository.get_series_by_id(series_id)
            if series is None:
                raise ValidationError({"series_id": ["Série introuvable."]})
        elif series_name:
            series = self.repository.get_or_create_series(series_name)

        event = self.repository.create_event(series=series, event_date=event_date, **clean_payload)
        self.session.commit()
        return self._serialize_event(event)

    def update_event(self, event_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        clean_payload = self._validate_event_payload(payload, require_title=False)
        if not clean_payload:
            return self.get_event(event_id)

        try:
            event = self.repository.get_event(event_id)
        except LookupError as exc:
            raise EventNotFoundError(str(exc)) from exc

        series_name = clean_payload.pop("series_name", None)
        series_id = clean_payload.pop("series_id", None)
        if series_name is not None or series_id is not None:
            if series_id is not None:
                if series_id == 0:
                    self.repository.assign_series(event, None)
                else:
                    series = self.repository.get_series_by_id(series_id)
                    if series is None:
                        raise ValidationError({"series_id": ["Série introuvable."]})
                    self.repository.assign_series(event, series)
            elif series_name:
                series = self.repository.get_or_create_series(series_name)
                self.repository.assign_series(event, series)

        if "event_date" in clean_payload:
            clean_payload["event_date"] = clean_payload["event_date"]

        updated_event = self.repository.update_event(event, clean_payload)
        self.session.commit()
        return self._serialize_event(updated_event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _validate_event_payload(
        self, data: Dict[str, Any], *, require_title: bool
    ) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise ValidationError(
                {
                    "_schema": [
                        "Payload JSON invalide: un objet JSON (type dict) est requis.",
                    ]
                }
            )

        errors: Dict[str, List[str]] = {}
        clean: Dict[str, Any] = {}

        if "title" in data or require_title:
            title = data.get("title")
            if not isinstance(title, str) or not title.strip():
                errors.setdefault("title", []).append(
                    "Champ requis (string non vide)."
                )
            else:
                clean["title"] = title.strip()

        if "attendees" in data:
            attendees = data["attendees"]
            if isinstance(attendees, bool) or not isinstance(attendees, int) or attendees < 0:
                errors.setdefault("attendees", []).append(
                    "Doit être un entier >= 0 (valeur booléenne non autorisée)."
                )
            else:
                clean["attendees"] = attendees
        elif require_title:
            clean.setdefault("attendees", 0)

        if "date" in data or require_title:
            provided_date = data.get("date")
            if provided_date is None:
                if require_title:
                    clean["event_date"] = date.today()
                else:
                    errors.setdefault("date", []).append(
                        "Doit être une chaîne au format YYYY-MM-DD."
                    )
            elif not isinstance(provided_date, str) or not provided_date.strip():
                errors.setdefault("date", []).append(
                    "Doit être une chaîne au format YYYY-MM-DD."
                )
            else:
                stripped = provided_date.strip()
                try:
                    clean["event_date"] = datetime.strptime(stripped, "%Y-%m-%d").date()
                except ValueError:
                    errors.setdefault("date", []).append(
                        "Format de date invalide, attendu YYYY-MM-DD."
                    )

        if "location" in data:
            location = data.get("location")
            clean["location"] = location.strip() if isinstance(location, str) else location
        elif require_title:
            clean.setdefault("location", "TBD")

        if "type" in data:
            event_type = data.get("type")
            clean["event_type"] = event_type.strip() if isinstance(event_type, str) else event_type
        elif require_title:
            clean.setdefault("event_type", "general")

        if "series" in data:
            series = data.get("series")
            if isinstance(series, dict):
                name = series.get("name")
                if isinstance(name, str) and name.strip():
                    clean["series_name"] = name.strip()
                else:
                    errors.setdefault("series", []).append(
                        "Champ 'name' requis pour la série."
                    )
            elif isinstance(series, str):
                if series.strip():
                    clean["series_name"] = series.strip()
                else:
                    errors.setdefault("series", []).append(
                        "Nom de série invalide."
                    )
            elif series is not None:
                errors.setdefault("series", []).append(
                    "Doit être une chaîne ou un objet contenant un champ 'name'."
                )

        if "series_id" in data:
            series_id = data.get("series_id")
            if series_id is None:
                if not require_title:
                    clean["series_id"] = 0
            elif not isinstance(series_id, int) or series_id < 0:
                errors.setdefault("series_id", []).append(
                    "Doit être un entier >= 0."
                )
            else:
                clean["series_id"] = series_id

        if errors:
            raise ValidationError(errors)

        return clean

    def _parse_filter_date(self, value: Optional[str], field: str) -> Optional[date]:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValidationError({field: ["Format de date invalide pour le filtre, attendu YYYY-MM-DD."]})
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValidationError({field: ["Format de date invalide pour le filtre, attendu YYYY-MM-DD."]}) from exc

    @staticmethod
    def _normalize_filter_value(value: Optional[str]) -> Optional[str]:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    def _serialize_event(self, event) -> Dict[str, Any]:
        return {
            "id": event.id,
            "title": event.title,
            "date": event.event_date.isoformat(),
            "location": event.location,
            "type": event.event_type,
            "attendees": event.attendees,
            "series": self._serialize_series(event.series),
            "created_at": self._serialize_datetime(event.created_at),
            "updated_at": self._serialize_datetime(event.updated_at),
        }

    @staticmethod
    def _serialize_series(series) -> Optional[Dict[str, Any]]:
        if series is None:
            return None
        return {"id": series.id, "name": series.name}

    @staticmethod
    def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None
