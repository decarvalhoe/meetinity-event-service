"""Services managing event speakers, organisers and sponsors."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.repositories.events import EventRepository
from src.repositories.partners import EventSpeakerRepository, EventSponsorRepository

__all__ = [
    "SpeakerService",
    "SpeakerValidationError",
    "SpeakerNotFoundError",
    "SponsorService",
    "SponsorValidationError",
    "SponsorNotFoundError",
]


class SpeakerValidationError(Exception):
    def __init__(self, errors: Dict[str, List[str]], message: str = "Validation échouée."):
        super().__init__(message)
        self.errors = errors
        self.message = message


class SpeakerNotFoundError(Exception):
    """Raised when a speaker or organiser cannot be located."""


class SponsorValidationError(Exception):
    def __init__(self, errors: Dict[str, List[str]], message: str = "Validation échouée."):
        super().__init__(message)
        self.errors = errors
        self.message = message


class SponsorNotFoundError(Exception):
    """Raised when a sponsor cannot be located."""


class SpeakerService:
    """Handle CRUD operations for speakers and organisers."""

    ALLOWED_ROLES = {"speaker", "organizer"}

    def __init__(self, session: Session) -> None:
        self.session = session
        self.event_repository = EventRepository(session)
        self.repository = EventSpeakerRepository(session)

    def add_profile(self, event_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_event_exists(event_id)
        clean = self._validate_payload(payload, require_name=True)
        if clean.get("display_order") is None:
            clean["display_order"] = self._next_display_order(event_id)
        speaker = self.repository.create(event_id=event_id, **clean)
        self.session.commit()
        return self._serialize_speaker(speaker)

    def update_profile(
        self, event_id: int, speaker_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        self._ensure_event_exists(event_id)
        speaker = self._get_speaker(event_id, speaker_id)
        clean = self._validate_payload(payload, require_name=False)
        if not clean:
            return self._serialize_speaker(speaker)
        updated = self.repository.update(speaker, clean)
        self.session.commit()
        return self._serialize_speaker(updated)

    def remove_profile(self, event_id: int, speaker_id: int) -> None:
        self._ensure_event_exists(event_id)
        speaker = self._get_speaker(event_id, speaker_id)
        self.repository.delete(speaker)
        self.session.commit()

    def list_profiles(self, event_id: int, role: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_event_exists(event_id)
        speakers = self.repository.list_for_event(event_id, role=role)
        return [self._serialize_speaker(speaker) for speaker in speakers]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_event_exists(self, event_id: int) -> None:
        try:
            self.event_repository.get_event(event_id)
        except LookupError as exc:
            raise SpeakerNotFoundError(str(exc)) from exc

    def _get_speaker(self, event_id: int, speaker_id: int):
        try:
            return self.repository.get(event_id, speaker_id)
        except LookupError as exc:
            raise SpeakerNotFoundError(str(exc)) from exc

    def _validate_payload(self, data: Dict[str, Any], *, require_name: bool) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise SpeakerValidationError(
                {"_schema": ["Payload JSON invalide: un objet est requis."]}
            )
        errors: Dict[str, List[str]] = {}
        clean: Dict[str, Any] = {}

        if "name" in data or require_name:
            name = data.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.setdefault("name", []).append("Nom complet requis.")
            else:
                clean["full_name"] = name.strip()

        if "role" in data:
            role = data.get("role")
            if role not in self.ALLOWED_ROLES:
                errors.setdefault("role", []).append("Type d'intervenant invalide.")
            else:
                clean["role"] = role

        for field in ["title", "company", "bio", "contact_email", "photo_url"]:
            if field in data:
                value = data.get(field)
                if value is None or isinstance(value, str):
                    clean[field] = value.strip() if isinstance(value, str) and value.strip() else value
                else:
                    errors.setdefault(field, []).append("Valeur invalide.")

        if "topics" in data:
            topics = data.get("topics")
            if topics is None or isinstance(topics, dict):
                clean["topics"] = topics
            else:
                errors.setdefault("topics", []).append("Thématiques invalides.")

        if "metadata" in data:
            metadata = data.get("metadata")
            if metadata is None or isinstance(metadata, dict):
                clean["metadata"] = metadata
            else:
                errors.setdefault("metadata", []).append("Métadonnées invalides.")

        if "display_order" in data:
            order = data.get("display_order")
            if isinstance(order, int) and order >= 0:
                clean["display_order"] = order
            else:
                errors.setdefault("display_order", []).append("Ordre d'affichage invalide.")

        if errors:
            raise SpeakerValidationError(errors)

        return clean

    def _next_display_order(self, event_id: int) -> int:
        speakers = self.repository.list_for_event(event_id)
        if not speakers:
            return 0
        return max(s.display_order for s in speakers) + 1

    def _serialize_speaker(self, speaker) -> Dict[str, Any]:
        return {
            "id": speaker.id,
            "event_id": speaker.event_id,
            "name": speaker.full_name,
            "role": speaker.role,
            "title": speaker.title,
            "company": speaker.company,
            "bio": speaker.bio,
            "topics": speaker.topics or {},
            "contact_email": speaker.contact_email,
            "photo_url": speaker.photo_url,
            "metadata": speaker.metadata or {},
            "display_order": speaker.display_order,
            "created_at": speaker.created_at.isoformat(),
        }


class SponsorService:
    """Handle sponsor management workflows."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.event_repository = EventRepository(session)
        self.repository = EventSponsorRepository(session)

    def add_sponsor(self, event_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_event_exists(event_id)
        clean = self._validate_payload(payload)
        if clean.get("display_order") is None:
            clean["display_order"] = self._next_display_order(event_id)
        sponsor = self.repository.create(event_id=event_id, **clean)
        self.session.commit()
        return self._serialize_sponsor(sponsor)

    def update_sponsor(
        self, event_id: int, sponsor_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        self._ensure_event_exists(event_id)
        sponsor = self._get_sponsor(event_id, sponsor_id)
        clean = self._validate_payload(payload, partial=True)
        if not clean:
            return self._serialize_sponsor(sponsor)
        updated = self.repository.update(sponsor, clean)
        self.session.commit()
        return self._serialize_sponsor(updated)

    def remove_sponsor(self, event_id: int, sponsor_id: int) -> None:
        self._ensure_event_exists(event_id)
        sponsor = self._get_sponsor(event_id, sponsor_id)
        self.repository.delete(sponsor)
        self.session.commit()

    def list_sponsors(self, event_id: int) -> List[Dict[str, Any]]:
        self._ensure_event_exists(event_id)
        sponsors = self.repository.list_for_event(event_id)
        return [self._serialize_sponsor(sponsor) for sponsor in sponsors]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_event_exists(self, event_id: int) -> None:
        try:
            self.event_repository.get_event(event_id)
        except LookupError as exc:
            raise SponsorNotFoundError(str(exc)) from exc

    def _get_sponsor(self, event_id: int, sponsor_id: int):
        try:
            return self.repository.get(event_id, sponsor_id)
        except LookupError as exc:
            raise SponsorNotFoundError(str(exc)) from exc

    def _validate_payload(self, data: Dict[str, Any], partial: bool = False) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise SponsorValidationError(
                {"_schema": ["Payload JSON invalide: un objet est requis."]}
            )
        errors: Dict[str, List[str]] = {}
        clean: Dict[str, Any] = {}

        if "name" in data or not partial:
            name = data.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.setdefault("name", []).append("Nom du sponsor requis.")
            else:
                clean["name"] = name.strip()

        for field in ["level", "description", "website", "logo_url", "contact_email"]:
            if field in data:
                value = data.get(field)
                if value is None or isinstance(value, str):
                    clean[field] = value.strip() if isinstance(value, str) and value.strip() else value
                else:
                    errors.setdefault(field, []).append("Valeur invalide.")

        if "metadata" in data:
            metadata = data.get("metadata")
            if metadata is None or isinstance(metadata, dict):
                clean["metadata"] = metadata
            else:
                errors.setdefault("metadata", []).append("Métadonnées invalides.")

        if "display_order" in data:
            order = data.get("display_order")
            if isinstance(order, int) and order >= 0:
                clean["display_order"] = order
            else:
                errors.setdefault("display_order", []).append("Ordre d'affichage invalide.")

        if errors:
            raise SponsorValidationError(errors)
        return clean

    def _next_display_order(self, event_id: int) -> int:
        sponsors = self.repository.list_for_event(event_id)
        if not sponsors:
            return 0
        return max(s.display_order for s in sponsors) + 1

    def _serialize_sponsor(self, sponsor) -> Dict[str, Any]:
        return {
            "id": sponsor.id,
            "event_id": sponsor.event_id,
            "name": sponsor.name,
            "level": sponsor.level,
            "description": sponsor.description,
            "website": sponsor.website,
            "logo_url": sponsor.logo_url,
            "contact_email": sponsor.contact_email,
            "metadata": sponsor.metadata or {},
            "display_order": sponsor.display_order,
            "created_at": sponsor.created_at.isoformat(),
        }
