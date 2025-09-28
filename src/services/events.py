"""Service layer for event orchestration and validation."""
from __future__ import annotations

import copy
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from src.models import EventCategory, EventSeries, EventTag
from src.repositories.catalogs import (
    CategoryRepository,
    SeriesRepository,
    TagRepository,
    TemplateRepository,
)
from src.repositories.events import EventRepository

__all__ = [
    "ApprovalWorkflowError",
    "EventNotFoundError",
    "EventService",
    "ValidationError",
    "CategoryService",
    "TagService",
    "SeriesService",
    "TemplateService",
]


LOCALE_PATTERN = re.compile(r"^[a-z]{2}(?:[-_][A-Z]{2})?$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_STATUSES = {"draft", "pending", "approved", "rejected"}


def is_valid_locale(value: str) -> bool:
    return bool(isinstance(value, str) and LOCALE_PATTERN.match(value))


def validate_translation_payload(
    payload: Dict[str, Any], *, require_locale: bool
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError({"_schema": ["Traduction invalide (objet attendu)."]})

    errors: Dict[str, List[str]] = {}
    clean: Dict[str, Any] = {}

    if "locale" in payload or require_locale:
        locale = payload.get("locale")
        if not isinstance(locale, str) or not is_valid_locale(locale):
            errors.setdefault("locale", []).append("Locale invalide.")
        else:
            clean["locale"] = locale.replace("_", "-")

    if "title" in payload or require_locale:
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.setdefault("title", []).append("Titre requis pour la traduction.")
        else:
            clean["title"] = title.strip()

    if "description" in payload:
        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            errors.setdefault("description", []).append("Description invalide.")
        else:
            clean["description"] = description

    if "fallback" in payload:
        fallback = payload.get("fallback")
        if not isinstance(fallback, bool):
            errors.setdefault("fallback", []).append("Doit être un booléen.")
        else:
            clean["fallback"] = fallback

    if errors:
        raise ValidationError(errors)

    return clean


class ValidationError(Exception):
    """Raised when incoming payload validation fails."""

    def __init__(self, errors: Dict[str, List[str]], message: str = "Validation échouée."):
        super().__init__(message)
        self.errors = errors
        self.message = message


class ApprovalWorkflowError(Exception):
    """Raised when an invalid status transition is requested."""

    def __init__(self, message: str):
        super().__init__(message)


class EventNotFoundError(Exception):
    """Raised when an event could not be located."""


class EventService:
    """High level operations for managing events."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = EventRepository(session)
        self.category_repository = CategoryRepository(session)
        self.tag_repository = TagRepository(session)
        self.series_repository = SeriesRepository(session)
        self.template_repository = TemplateRepository(session)

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
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        cleaned_type = self._normalize_filter_value(event_type)
        cleaned_location = self._normalize_filter_value(location)
        before_value = self._normalize_filter_value(before)
        after_value = self._normalize_filter_value(after)
        status_value = self._normalize_filter_value(status)

        if status_value and status_value not in ALLOWED_STATUSES:
            raise ValidationError({"status": ["Statut inconnu."]})

        before_date = self._parse_filter_date(before_value, "before")
        after_date = self._parse_filter_date(after_value, "after")

        events = self.repository.list_events(
            event_type=cleaned_type,
            location=cleaned_location,
            before=before_date,
            after=after_date,
            status=status_value,
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
        series = self._resolve_series(clean_payload)
        categories = self._resolve_categories(clean_payload)
        tags = self._resolve_tags(clean_payload)
        translations = clean_payload.pop("translations", [])
        clean_payload.pop("_series_specified", None)
        clean_payload.pop("_categories_specified", None)
        clean_payload.pop("_tags_specified", None)

        event = self.repository.create_event(
            title=clean_payload.get("title"),
            event_date=event_date,
            location=clean_payload.get("location"),
            event_type=clean_payload.get("event_type"),
            attendees=clean_payload.get("attendees", 0),
            timezone=clean_payload.get("timezone", "UTC"),
            status=clean_payload.get("status", "draft"),
            capacity_limit=clean_payload.get("capacity_limit"),
            recurrence_rule=clean_payload.get("recurrence_rule"),
            default_locale=clean_payload.get("default_locale", "fr"),
            fallback_locale=clean_payload.get("fallback_locale"),
            organizer_email=clean_payload.get("organizer_email"),
            settings=clean_payload.get("settings"),
            series=series,
            template=None,
            categories=categories,
            tags=tags,
        )

        for translation in translations:
            self.repository.upsert_translation(
                event,
                locale=translation["locale"],
                title=translation["title"],
                description=translation.get("description"),
                fallback=translation.get("fallback"),
            )

        try:
            self._ensure_capacity_constraints(event)
        except ValidationError:
            self.session.rollback()
            raise

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

        series = self._resolve_series(clean_payload, current_event=event)
        categories = self._resolve_categories(clean_payload)
        tags = self._resolve_tags(clean_payload)
        translations = clean_payload.pop("translations", None)
        series_specified = clean_payload.pop("_series_specified", False)
        categories_specified = clean_payload.pop("_categories_specified", False)
        tags_specified = clean_payload.pop("_tags_specified", False)

        updates = {}
        for field in [
            "title",
            "location",
            "event_type",
            "attendees",
            "event_date",
            "timezone",
            "status",
            "capacity_limit",
            "recurrence_rule",
            "default_locale",
            "fallback_locale",
            "organizer_email",
            "settings",
        ]:
            if field in clean_payload:
                updates[field] = clean_payload[field]

        if updates:
            event = self.repository.update_event(event, updates)

        if series_specified:
            self.repository.assign_series(event, series)

        if categories_specified:
            self.repository.assign_categories(event, categories)

        if tags_specified:
            self.repository.assign_tags(event, tags)

        if translations is not None:
            for translation in translations:
                self.repository.upsert_translation(
                    event,
                    locale=translation["locale"],
                    title=translation["title"],
                    description=translation.get("description"),
                    fallback=translation.get("fallback"),
                )

        try:
            self._ensure_capacity_constraints(event)
        except ValidationError:
            self.session.rollback()
            raise

        self.session.commit()
        return self._serialize_event(event)

    def create_event_from_template(
        self, template_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            template = self.template_repository.get(template_id)
        except LookupError as exc:
            raise ValidationError({"template_id": [str(exc)]}) from exc

        merged_payload = self._build_payload_from_template(template, payload)
        clean_payload = self._validate_event_payload(merged_payload, require_title=True)

        event_date = clean_payload.pop("event_date", date.today())
        series = self._resolve_series(clean_payload)
        categories = self._resolve_categories(clean_payload)
        tags = self._resolve_tags(clean_payload)
        translations = clean_payload.pop("translations", [])
        clean_payload.pop("_series_specified", None)
        clean_payload.pop("_categories_specified", None)
        clean_payload.pop("_tags_specified", None)

        event = self.repository.create_event(
            title=clean_payload.get("title"),
            event_date=event_date,
            location=clean_payload.get("location"),
            event_type=clean_payload.get("event_type", template.description),
            attendees=clean_payload.get("attendees", 0),
            timezone=clean_payload.get("timezone", template.default_timezone),
            status=clean_payload.get("status", "draft"),
            capacity_limit=clean_payload.get("capacity_limit", template.default_capacity_limit),
            recurrence_rule=clean_payload.get("recurrence_rule"),
            default_locale=clean_payload.get("default_locale", template.default_locale),
            fallback_locale=clean_payload.get("fallback_locale", template.fallback_locale),
            organizer_email=clean_payload.get("organizer_email"),
            settings=clean_payload.get("settings"),
            series=series,
            template=template,
            categories=categories,
            tags=tags,
        )

        for translation in translations or self._default_template_translations(template):
            self.repository.upsert_translation(
                event,
                locale=translation["locale"],
                title=translation["title"],
                description=translation.get("description"),
                fallback=translation.get("fallback"),
            )

        try:
            self._ensure_capacity_constraints(event)
        except ValidationError:
            self.session.rollback()
            raise

        self.session.commit()
        return self._serialize_event(event)

    def upsert_translation(
        self, event_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        translation_payload = validate_translation_payload(payload, require_locale=True)
        try:
            event = self.repository.get_event(event_id)
        except LookupError as exc:
            raise EventNotFoundError(str(exc)) from exc

        translation = self.repository.upsert_translation(
            event,
            locale=translation_payload["locale"],
            title=translation_payload["title"],
            description=translation_payload.get("description"),
            fallback=translation_payload.get("fallback"),
        )
        self.session.commit()
        return self._serialize_translation(translation, event)

    def delete_translation(self, event_id: int, locale: str) -> None:
        if not locale or not isinstance(locale, str):
            raise ValidationError({"locale": ["Locale invalide."]})
        try:
            event = self.repository.get_event(event_id)
        except LookupError as exc:
            raise EventNotFoundError(str(exc)) from exc

        try:
            self.repository.remove_translation(event, locale)
        except LookupError as exc:
            raise ValidationError({"locale": [str(exc)]}) from exc

        self.session.commit()

    def submit_for_approval(self, event_id: int, actor: Optional[str], notes: Optional[str]) -> Dict[str, Any]:
        return self._transition_status(event_id, "pending", actor, notes)

    def approve_event(self, event_id: int, actor: Optional[str], notes: Optional[str]) -> Dict[str, Any]:
        return self._transition_status(event_id, "approved", actor, notes)

    def reject_event(self, event_id: int, actor: Optional[str], notes: Optional[str]) -> Dict[str, Any]:
        return self._transition_status(event_id, "rejected", actor, notes)

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

        if "timezone" in data or require_title:
            timezone = data.get("timezone", "UTC")
            if timezone is None:
                timezone = "UTC"
            if not isinstance(timezone, str) or not timezone.strip():
                errors.setdefault("timezone", []).append("Fuseau horaire invalide.")
            else:
                try:
                    ZoneInfo(timezone.strip())
                    clean["timezone"] = timezone.strip()
                except ZoneInfoNotFoundError:
                    errors.setdefault("timezone", []).append("Fuseau horaire introuvable.")

        if "status" in data or require_title:
            status = data.get("status", "draft")
            if status not in ALLOWED_STATUSES:
                errors.setdefault("status", []).append("Statut inconnu.")
            else:
                clean["status"] = status

        if "capacity_limit" in data:
            capacity = data.get("capacity_limit")
            if capacity is None:
                clean["capacity_limit"] = None
            elif isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0:
                errors.setdefault("capacity_limit", []).append(
                    "Doit être un entier >= 0 ou null."
                )
            else:
                clean["capacity_limit"] = capacity

        if "capacity_limit" in clean and "attendees" in clean:
            capacity = clean.get("capacity_limit")
            attendees_value = clean.get("attendees", 0)
            if capacity is not None and attendees_value is not None and capacity < attendees_value:
                errors.setdefault("capacity_limit", []).append(
                    "La capacité doit être supérieure ou égale au nombre de participants."
                )

        if "recurrence_rule" in data:
            rule = data.get("recurrence_rule")
            if rule is None or not isinstance(rule, str) or "FREQ" not in rule.upper():
                errors.setdefault("recurrence_rule", []).append(
                    "Règle de récurrence invalide (doit contenir FREQ)."
                )
            else:
                clean["recurrence_rule"] = rule

        if "default_locale" in data or require_title:
            locale = data.get("default_locale", "fr")
            if not isinstance(locale, str) or not is_valid_locale(locale):
                errors.setdefault("default_locale", []).append("Locale invalide.")
            else:
                clean["default_locale"] = locale.replace("_", "-")

        if "fallback_locale" in data:
            fallback_locale = data.get("fallback_locale")
            if fallback_locale is None:
                clean["fallback_locale"] = None
            elif not isinstance(fallback_locale, str) or not is_valid_locale(fallback_locale):
                errors.setdefault("fallback_locale", []).append("Locale fallback invalide.")
            else:
                clean["fallback_locale"] = fallback_locale.replace("_", "-")

        if "organizer_email" in data:
            organizer_email = data.get("organizer_email")
            if organizer_email is None:
                clean["organizer_email"] = None
            elif not isinstance(organizer_email, str) or not EMAIL_PATTERN.match(organizer_email):
                errors.setdefault("organizer_email", []).append("Email invalide.")
            else:
                clean["organizer_email"] = organizer_email

        if "settings" in data:
            settings = data.get("settings")
            if settings is None:
                clean["settings"] = None
            elif not isinstance(settings, dict):
                errors.setdefault("settings", []).append("Doit être un objet JSON.")
            else:
                clean["settings"] = copy.deepcopy(settings)

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
                clean["series_id"] = None
            elif not isinstance(series_id, int) or series_id < 0:
                errors.setdefault("series_id", []).append(
                    "Doit être un entier >= 0."
                )
            else:
                clean["series_id"] = series_id

        if "category_ids" in data:
            clean["category_ids"], cat_errors = self._validate_id_list(data["category_ids"], "category_ids")
            if cat_errors:
                errors.setdefault("category_ids", []).extend(cat_errors)

        if "tag_ids" in data:
            clean["tag_ids"], tag_errors = self._validate_id_list(data["tag_ids"], "tag_ids")
            if tag_errors:
                errors.setdefault("tag_ids", []).extend(tag_errors)

        if "translations" in data:
            translations = data.get("translations")
            if translations is None:
                clean["translations"] = []
            elif not isinstance(translations, list):
                errors.setdefault("translations", []).append("Doit être une liste de traductions.")
            else:
                parsed_translations = []
                for idx, translation in enumerate(translations):
                    try:
                        parsed = validate_translation_payload(translation, require_locale=True)
                    except ValidationError as exc:
                        for key, messages in exc.errors.items():
                            errors.setdefault(f"translations[{idx}].{key}", []).extend(messages)
                    else:
                        parsed_translations.append(parsed)
                if parsed_translations:
                    clean["translations"] = parsed_translations

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

    def _validate_id_list(self, value: Any, field: str) -> Tuple[List[int], List[str]]:
        if value is None:
            return [], []
        if not isinstance(value, list):
            return [], ["Doit être une liste d'identifiants entiers."]
        ids: List[int] = []
        errors: List[str] = []
        for item in value:
            if not isinstance(item, int) or item < 0:
                errors.append("Chaque identifiant doit être un entier >= 0.")
            else:
                ids.append(item)
        return ids, errors

    def _resolve_series(
        self, payload: Dict[str, Any], current_event=None
    ) -> Optional[EventSeries]:
        series_specified = "series_id" in payload or "series_name" in payload
        series_id = payload.pop("series_id", None) if "series_id" in payload else None
        series_name = payload.pop("series_name", None) if "series_name" in payload else None

        if series_id is not None:
            if series_id == 0:
                payload["_series_specified"] = True
                return None
            try:
                series = self.series_repository.get(series_id)
                payload["_series_specified"] = True
                return series
            except LookupError as exc:
                raise ValidationError({"series_id": [str(exc)]}) from exc

        if series_name:
            existing = self.series_repository.get_by_name(series_name)
            if existing:
                payload["_series_specified"] = True
                return existing
            payload["_series_specified"] = True
            return self.series_repository.create(name=series_name, description=None)

        if series_specified:
            payload["_series_specified"] = True
            return None

        if current_event is not None:
            return current_event.series
        return None

    def _resolve_categories(self, payload: Dict[str, Any]) -> Optional[List[EventCategory]]:
        if "category_ids" not in payload:
            return None
        category_ids = payload.pop("category_ids", [])
        payload["_categories_specified"] = True
        if not category_ids:
            return []
        categories = []
        missing = []
        for category_id in category_ids:
            category = self.session.get(EventCategory, category_id)
            if category is None:
                missing.append(str(category_id))
            else:
                categories.append(category)
        if missing:
            raise ValidationError({"category_ids": [f"Catégories introuvables: {', '.join(missing)}"]})
        return categories

    def _resolve_tags(self, payload: Dict[str, Any]) -> Optional[List[EventTag]]:
        if "tag_ids" not in payload:
            return None
        tag_ids = payload.pop("tag_ids", [])
        payload["_tags_specified"] = True
        if not tag_ids:
            return []
        tags = []
        missing = []
        for tag_id in tag_ids:
            tag = self.session.get(EventTag, tag_id)
            if tag is None:
                missing.append(str(tag_id))
            else:
                tags.append(tag)
        if missing:
            raise ValidationError({"tag_ids": [f"Tags introuvables: {', '.join(missing)}"]})
        return tags

    def _ensure_capacity_constraints(self, event) -> None:
        if event.capacity_limit is not None and event.capacity_limit < event.attendees:
            raise ValidationError(
                {"capacity_limit": ["La capacité doit être supérieure ou égale au nombre de participants."]}
            )

    def _build_payload_from_template(self, template, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = {
            "title": payload.get("title") or template.name,
            "date": payload.get("date"),
            "location": payload.get("location"),
            "type": payload.get("type") or template.description,
            "attendees": payload.get("attendees", 0),
            "timezone": payload.get("timezone") or template.default_timezone,
            "status": payload.get("status", "draft"),
            "capacity_limit": payload.get("capacity_limit", template.default_capacity_limit),
            "recurrence_rule": payload.get("recurrence_rule"),
            "default_locale": payload.get("default_locale", template.default_locale),
            "fallback_locale": payload.get("fallback_locale", template.fallback_locale),
            "organizer_email": payload.get("organizer_email"),
            "settings": self._merge_settings(template.default_metadata, payload.get("settings")),
            "series_id": payload.get("series_id"),
            "series_name": payload.get("series_name"),
            "category_ids": payload.get("category_ids"),
            "tag_ids": payload.get("tag_ids"),
            "translations": payload.get("translations"),
        }
        return merged

    @staticmethod
    def _merge_settings(template_settings: Optional[dict], event_settings: Optional[dict]) -> Optional[dict]:
        if template_settings is None and event_settings is None:
            return None
        merged = {}
        if isinstance(template_settings, dict):
            merged.update(template_settings)
        if isinstance(event_settings, dict):
            merged.update(event_settings)
        return merged

    def _default_template_translations(self, template) -> Iterable[Dict[str, Any]]:
        for translation in template.translations:
            yield {
                "locale": translation.locale,
                "title": translation.title,
                "description": translation.description,
                "fallback": translation.locale == template.fallback_locale,
            }

    def _transition_status(
        self, event_id: int, new_status: str, actor: Optional[str], notes: Optional[str]
    ) -> Dict[str, Any]:
        try:
            event = self.repository.get_event(event_id)
        except LookupError as exc:
            raise EventNotFoundError(str(exc)) from exc

        current_status = event.status
        allowed_transitions = {
            "draft": {"pending"},
            "pending": {"approved", "rejected"},
            "rejected": {"pending"},
            "approved": set(),
        }
        if new_status not in allowed_transitions.get(current_status, set()):
            raise ApprovalWorkflowError(
                f"Transition de {current_status} vers {new_status} non autorisée."
            )

        log = self.repository.log_status_change(
            event,
            previous_status=current_status,
            new_status=new_status,
            actor=actor,
            notes=notes,
        )

        if event.organizer_email:
            message = f"Votre événement '{event.title}' est désormais {new_status}."
            self.repository.create_notification(
                event,
                recipient=event.organizer_email,
                message=message,
            )

        self.session.commit()
        return {
            "event": self._serialize_event(event),
            "log": {
                "id": log.id,
                "previous_status": log.previous_status,
                "new_status": log.new_status,
                "actor": log.actor,
                "notes": log.notes,
                "created_at": log.created_at.isoformat(),
            },
        }

    def _serialize_event(self, event) -> Dict[str, Any]:
        return {
            "id": event.id,
            "title": event.title,
            "date": event.event_date.isoformat() if event.event_date else None,
            "location": event.location,
            "type": event.event_type,
            "attendees": event.attendees,
            "timezone": event.timezone,
            "status": event.status,
            "capacity_limit": event.capacity_limit,
            "recurrence_rule": event.recurrence_rule,
            "default_locale": event.default_locale,
            "fallback_locale": event.fallback_locale,
            "organizer_email": event.organizer_email,
            "settings": copy.deepcopy(event.settings) if event.settings else None,
            "series": self._serialize_series(event.series),
            "template_id": event.template_id,
            "categories": [self._serialize_category(category) for category in event.categories],
            "tags": [self._serialize_tag(tag) for tag in event.tags],
            "translations": [self._serialize_translation(t, event) for t in event.translations],
            "created_at": self._serialize_datetime(event.created_at),
            "updated_at": self._serialize_datetime(event.updated_at),
        }

    @staticmethod
    def _serialize_series(series) -> Optional[Dict[str, Any]]:
        if series is None:
            return None
        return {"id": series.id, "name": series.name, "description": series.description}

    @staticmethod
    def _serialize_category(category) -> Dict[str, Any]:
        return {"id": category.id, "name": category.name, "description": category.description}

    @staticmethod
    def _serialize_tag(tag) -> Dict[str, Any]:
        return {"id": tag.id, "name": tag.name}

    @staticmethod
    def _serialize_translation(translation, event=None) -> Dict[str, Any]:
        return {
            "locale": translation.locale,
            "title": translation.title,
            "description": translation.description,
            "fallback": bool(event and event.fallback_locale == translation.locale),
        }

    @staticmethod
    def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None


class CatalogBaseService:
    """Base class for catalog management services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _ensure_name(self, payload: Dict[str, Any], field: str = "name") -> str:
        name = payload.get(field)
        if not isinstance(name, str) or not name.strip():
            raise ValidationError({field: ["Nom requis."]})
        return name.strip()


class CategoryService(CatalogBaseService):
    """Service for managing event categories."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.repository = CategoryRepository(session)

    def list_categories(self) -> List[Dict[str, Any]]:
        categories = self.repository.list()
        return [self._serialize(category) for category in categories]

    def get_category(self, category_id: int) -> Dict[str, Any]:
        try:
            category = self.repository.get(category_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        return self._serialize(category)

    def create_category(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = self._ensure_name(payload)
        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            raise ValidationError({"description": ["Description invalide."]})
        category = self.repository.create(name=name, description=description)
        self.session.commit()
        return self._serialize(category)

    def update_category(self, category_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            category = self.repository.get(category_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc

        name = payload.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValidationError({"name": ["Nom invalide."]})
        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            raise ValidationError({"description": ["Description invalide."]})

        category = self.repository.update(
            category,
            name=name.strip() if isinstance(name, str) and name.strip() else None,
            description=description,
        )
        self.session.commit()
        return self._serialize(category)

    def delete_category(self, category_id: int) -> None:
        try:
            category = self.repository.get(category_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        self.repository.delete(category)
        self.session.commit()

    @staticmethod
    def _serialize(category) -> Dict[str, Any]:
        return {"id": category.id, "name": category.name, "description": category.description}


class TagService(CatalogBaseService):
    """Service for managing event tags."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.repository = TagRepository(session)

    def list_tags(self) -> List[Dict[str, Any]]:
        tags = self.repository.list()
        return [self._serialize(tag) for tag in tags]

    def get_tag(self, tag_id: int) -> Dict[str, Any]:
        try:
            tag = self.repository.get(tag_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        return self._serialize(tag)

    def create_tag(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = self._ensure_name(payload)
        tag = self.repository.create(name=name)
        self.session.commit()
        return self._serialize(tag)

    def update_tag(self, tag_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            tag = self.repository.get(tag_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc

        name = payload.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValidationError({"name": ["Nom invalide."]})

        tag = self.repository.update(tag, name=name.strip() if isinstance(name, str) and name.strip() else None)
        self.session.commit()
        return self._serialize(tag)

    def delete_tag(self, tag_id: int) -> None:
        try:
            tag = self.repository.get(tag_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        self.repository.delete(tag)
        self.session.commit()

    @staticmethod
    def _serialize(tag) -> Dict[str, Any]:
        return {"id": tag.id, "name": tag.name}


class SeriesService(CatalogBaseService):
    """Service for managing event series."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.repository = SeriesRepository(session)

    def list_series(self) -> List[Dict[str, Any]]:
        series_list = self.repository.list()
        return [self._serialize(series) for series in series_list]

    def get_series(self, series_id: int) -> Dict[str, Any]:
        try:
            series = self.repository.get(series_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        return self._serialize(series)

    def create_series(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = self._ensure_name(payload)
        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            raise ValidationError({"description": ["Description invalide."]})
        series = self.repository.create(name=name, description=description)
        self.session.commit()
        return self._serialize(series)

    def update_series(self, series_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            series = self.repository.get(series_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc

        name = payload.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValidationError({"name": ["Nom invalide."]})
        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            raise ValidationError({"description": ["Description invalide."]})

        series = self.repository.update(
            series,
            name=name.strip() if isinstance(name, str) and name.strip() else None,
            description=description,
        )
        self.session.commit()
        return self._serialize(series)

    def delete_series(self, series_id: int) -> None:
        try:
            series = self.repository.get(series_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        self.repository.delete(series)
        self.session.commit()

    @staticmethod
    def _serialize(series) -> Dict[str, Any]:
        return {
            "id": series.id,
            "name": series.name,
            "description": series.description,
        }


class TemplateService(CatalogBaseService):
    """Service for managing event templates."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.repository = TemplateRepository(session)

    def list_templates(self) -> List[Dict[str, Any]]:
        templates = self.repository.list()
        return [self._serialize(template) for template in templates]

    def get_template(self, template_id: int) -> Dict[str, Any]:
        try:
            template = self.repository.get(template_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        return self._serialize(template)

    def create_template(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = self._ensure_name(payload)
        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            raise ValidationError({"description": ["Description invalide."]})

        default_duration = self._validate_optional_int(payload.get("default_duration_minutes"), "default_duration_minutes")
        default_capacity = self._validate_optional_int(payload.get("default_capacity_limit"), "default_capacity_limit")
        timezone = payload.get("default_timezone", "UTC")
        if not isinstance(timezone, str) or not timezone.strip():
            raise ValidationError({"default_timezone": ["Fuseau horaire invalide."]})
        try:
            ZoneInfo(timezone.strip())
        except ZoneInfoNotFoundError as exc:
            raise ValidationError({"default_timezone": ["Fuseau horaire introuvable."]}) from exc

        default_locale = payload.get("default_locale", "fr")
        if not isinstance(default_locale, str) or not is_valid_locale(default_locale):
            raise ValidationError({"default_locale": ["Locale invalide."]})

        fallback_locale = payload.get("fallback_locale")
        if fallback_locale is not None and (not isinstance(fallback_locale, str) or not is_valid_locale(fallback_locale)):
            raise ValidationError({"fallback_locale": ["Locale invalide."]})

        default_metadata = payload.get("default_metadata")
        if default_metadata is not None and not isinstance(default_metadata, dict):
            raise ValidationError({"default_metadata": ["Doit être un objet JSON."]})

        template = self.repository.create(
            name=name,
            description=description,
            default_duration_minutes=default_duration,
            default_timezone=timezone.strip(),
            default_locale=default_locale.replace("_", "-"),
            fallback_locale=fallback_locale.replace("_", "-") if isinstance(fallback_locale, str) else None,
            default_capacity_limit=default_capacity,
            default_metadata=copy.deepcopy(default_metadata) if default_metadata else None,
        )
        self.session.commit()
        return self._serialize(template)

    def update_template(self, template_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            template = self.repository.get(template_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc

        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            raise ValidationError({"description": ["Description invalide."]})

        default_duration = self._validate_optional_int(payload.get("default_duration_minutes"), "default_duration_minutes")
        default_capacity = self._validate_optional_int(payload.get("default_capacity_limit"), "default_capacity_limit")

        timezone = payload.get("default_timezone")
        if timezone is not None:
            if not isinstance(timezone, str) or not timezone.strip():
                raise ValidationError({"default_timezone": ["Fuseau horaire invalide."]})
            try:
                ZoneInfo(timezone.strip())
            except ZoneInfoNotFoundError as exc:
                raise ValidationError({"default_timezone": ["Fuseau horaire introuvable."]}) from exc

        default_locale = payload.get("default_locale")
        if default_locale is not None and (not isinstance(default_locale, str) or not is_valid_locale(default_locale)):
            raise ValidationError({"default_locale": ["Locale invalide."]})

        fallback_locale = payload.get("fallback_locale")
        if fallback_locale is not None and fallback_locale != "" and (not isinstance(fallback_locale, str) or not is_valid_locale(fallback_locale)):
            raise ValidationError({"fallback_locale": ["Locale invalide."]})

        default_metadata = payload.get("default_metadata")
        if default_metadata is not None and default_metadata != {} and not isinstance(default_metadata, dict):
            raise ValidationError({"default_metadata": ["Doit être un objet JSON."]})

        template = self.repository.update(
            template,
            description=description,
            default_duration_minutes=default_duration,
            default_timezone=timezone.strip() if isinstance(timezone, str) else None,
            default_locale=default_locale.replace("_", "-") if isinstance(default_locale, str) else None,
            fallback_locale=fallback_locale.replace("_", "-") if isinstance(fallback_locale, str) else fallback_locale,
            default_capacity_limit=default_capacity,
            default_metadata=copy.deepcopy(default_metadata) if isinstance(default_metadata, dict) else None,
        )
        self.session.commit()
        return self._serialize(template)

    def delete_template(self, template_id: int) -> None:
        try:
            template = self.repository.get(template_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        self.repository.delete(template)
        self.session.commit()

    def upsert_translation(self, template_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            template = self.repository.get(template_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc

        translation_payload = {
            "locale": payload.get("locale"),
            "title": payload.get("title"),
            "description": payload.get("description"),
        }
        parsed = validate_translation_payload(translation_payload, require_locale=True)
        translation = self.repository.upsert_translation(
            template,
            locale=parsed["locale"],
            title=parsed["title"],
            description=parsed.get("description"),
        )
        self.session.commit()
        return self._serialize_translation(translation)

    def delete_translation(self, template_id: int, locale: str) -> None:
        if not isinstance(locale, str) or not locale:
            raise ValidationError({"locale": ["Locale invalide."]})
        try:
            template = self.repository.get(template_id)
        except LookupError as exc:
            raise ValidationError({"id": [str(exc)]}) from exc
        try:
            self.repository.remove_translation(template, locale)
        except LookupError as exc:
            raise ValidationError({"locale": [str(exc)]}) from exc
        self.session.commit()

    def _serialize(self, template) -> Dict[str, Any]:
        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "default_duration_minutes": template.default_duration_minutes,
            "default_timezone": template.default_timezone,
            "default_locale": template.default_locale,
            "fallback_locale": template.fallback_locale,
            "default_capacity_limit": template.default_capacity_limit,
            "default_metadata": copy.deepcopy(template.default_metadata) if template.default_metadata else None,
            "translations": [self._serialize_translation(t) for t in template.translations],
        }

    @staticmethod
    def _serialize_translation(translation) -> Dict[str, Any]:
        return {
            "locale": translation.locale,
            "title": translation.title,
            "description": translation.description,
        }

    def _validate_optional_int(self, value: Any, field: str) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValidationError({field: ["Doit être un entier >= 0 ou null."]})
        return value

