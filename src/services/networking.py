"""Networking orchestration service for participant matchmaking."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from src.models import ParticipantProfile
from src.repositories.events import EventRepository
from src.repositories.networking import (
    NetworkingSuggestionRepository,
    ParticipantProfileRepository,
)

__all__ = ["NetworkingService", "NetworkingValidationError", "ProfileNotFoundError"]


class NetworkingValidationError(Exception):
    """Raised when networking payload validation fails."""

    def __init__(self, errors: Dict[str, List[str]], message: str = "Validation échouée."):
        super().__init__(message)
        self.errors = errors
        self.message = message


class ProfileNotFoundError(Exception):
    """Raised when a participant profile could not be located."""


class NetworkingService:
    """Coordinate networking profile ingestion and matchmaking."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.event_repository = EventRepository(session)
        self.profile_repository = ParticipantProfileRepository(session)
        self.suggestion_repository = NetworkingSuggestionRepository(session)

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------
    def register_profile(self, event_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_event_exists(event_id)
        clean = self._validate_profile_payload(payload)

        profile = self.profile_repository.upsert(
            event_id=event_id,
            attendee_email=clean["attendee_email"],
            attendee_name=clean.get("attendee_name"),
            company=clean.get("company"),
            bio=clean.get("bio"),
            headline=clean.get("headline"),
            interests=clean.get("interests"),
            goals=clean.get("goals"),
            availability=clean.get("availability"),
            metadata=clean.get("metadata"),
        )

        self.session.commit()
        return self._serialize_profile(profile)

    def list_profiles(self, event_id: int) -> List[Dict[str, Any]]:
        self._ensure_event_exists(event_id)
        profiles = self.profile_repository.list_for_event(event_id)
        return [self._serialize_profile(profile) for profile in profiles]

    # ------------------------------------------------------------------
    # Suggestion workflow
    # ------------------------------------------------------------------
    def generate_suggestions(
        self,
        event_id: int,
        *,
        participant_email: Optional[str] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        if limit is not None and limit < 0:
            raise NetworkingValidationError({"limit": ["Doit être positif."]})

        self._ensure_event_exists(event_id)
        profiles = list(self.profile_repository.list_for_event(event_id))
        if not profiles:
            return []

        if participant_email:
            target = next(
                (p for p in profiles if p.attendee_email == participant_email),
                None,
            )
            if target is None:
                raise ProfileNotFoundError(
                    f"Profil {participant_email} introuvable pour l'événement {event_id}"
                )
            targets = [target]
        else:
            targets = profiles

        for profile in targets:
            ranked = self._rank_candidates(profile, profiles)
            capped = ranked if limit is None else ranked[:limit]
            for score, rationale, metadata, candidate in capped:
                self.suggestion_repository.upsert(
                    event_id=event_id,
                    participant_id=profile.id,
                    suggested_participant_id=candidate.id,
                    score=score,
                    rationale=rationale,
                    metadata=metadata,
                    status="pending",
                )

        self.session.commit()

        if participant_email:
            stored = self.suggestion_repository.list_for_participant(targets[0].id)
        else:
            stored = self.suggestion_repository.list_for_event(event_id)
        return [self._serialize_suggestion(s) for s in stored]

    def list_suggestions(
        self, event_id: int, *, participant_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        self._ensure_event_exists(event_id)
        if participant_email:
            profile = self.profile_repository.get_by_event_and_email(event_id, participant_email)
            if profile is None:
                raise ProfileNotFoundError(
                    f"Profil {participant_email} introuvable pour l'événement {event_id}"
                )
            suggestions = self.suggestion_repository.list_for_participant(profile.id)
        else:
            suggestions = self.suggestion_repository.list_for_event(event_id)
        return [self._serialize_suggestion(s) for s in suggestions]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_event_exists(self, event_id: int) -> None:
        try:
            self.event_repository.get_event(event_id)
        except LookupError as exc:
            raise ProfileNotFoundError(str(exc)) from exc

    def _validate_profile_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise NetworkingValidationError(
                {"_schema": ["Payload JSON invalide: un objet est attendu."]}
            )

        errors: Dict[str, List[str]] = {}
        clean: Dict[str, Any] = {}

        email = data.get("email")
        if not isinstance(email, str) or not email.strip():
            errors.setdefault("email", []).append("Adresse email requise.")
        else:
            clean["attendee_email"] = email.strip().lower()

        if "name" in data:
            name = data.get("name")
            if name is None:
                clean["attendee_name"] = None
            elif not isinstance(name, str) or not name.strip():
                errors.setdefault("name", []).append("Nom invalide.")
            else:
                clean["attendee_name"] = name.strip()

        if "company" in data:
            company = data.get("company")
            clean["company"] = company.strip() if isinstance(company, str) else company

        if "bio" in data:
            bio = data.get("bio")
            if bio is None or isinstance(bio, str):
                clean["bio"] = bio
            else:
                errors.setdefault("bio", []).append("Bio invalide.")

        if "headline" in data:
            headline = data.get("headline")
            if headline is None or isinstance(headline, str):
                clean["headline"] = headline.strip() if isinstance(headline, str) else None
            else:
                errors.setdefault("headline", []).append("Entête invalide.")

        if "interests" in data:
            interests = self._sanitize_string_list(data.get("interests"), "interests")
            if interests is not None:
                clean["interests"] = {"items": interests}
            else:
                errors.setdefault("interests", []).append("Liste d'intérêts invalide.")

        if "goals" in data:
            goals = self._sanitize_string_list(data.get("goals"), "goals")
            if goals is not None:
                clean["goals"] = {"items": goals}
            else:
                errors.setdefault("goals", []).append("Objectifs invalides.")

        if "availability" in data:
            availability = self._sanitize_string_list(data.get("availability"), "availability")
            if availability is not None:
                clean["availability"] = {"slots": availability}
            else:
                errors.setdefault("availability", []).append("Plages horaires invalides.")

        metadata = data.get("metadata")
        if metadata is not None:
            if isinstance(metadata, dict):
                clean["metadata"] = metadata
            else:
                errors.setdefault("metadata", []).append("Métadonnées invalides.")

        if errors:
            raise NetworkingValidationError(errors)

        return clean

    def _sanitize_string_list(self, value: Any, field: str) -> Optional[List[str]]:
        if value is None:
            return []
        if isinstance(value, dict):
            if "items" in value and isinstance(value["items"], Iterable):
                value = value["items"]
            elif "slots" in value and isinstance(value["slots"], Iterable):
                value = value["slots"]
            else:
                return None
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            return None
        cleaned: List[str] = []
        for entry in value:
            if not isinstance(entry, str):
                continue
            normalized = entry.strip()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def _rank_candidates(
        self,
        profile: ParticipantProfile,
        candidates: Sequence[ParticipantProfile],
    ) -> List[Tuple[float, str, Dict[str, Any], ParticipantProfile]]:
        ranked: List[Tuple[float, str, Dict[str, Any], ParticipantProfile]] = []
        for candidate in candidates:
            if candidate.id == profile.id:
                continue
            score, rationale, metadata = self._score_pair(profile, candidate)
            if score <= 0:
                continue
            ranked.append((score, rationale, metadata, candidate))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked

    def _score_pair(
        self, first: ParticipantProfile, second: ParticipantProfile
    ) -> Tuple[float, str, Dict[str, Any]]:
        first_interests = set(self._extract_list(first.interests, "items"))
        second_interests = set(self._extract_list(second.interests, "items"))
        shared_interests = sorted(first_interests & second_interests)

        first_goals = set(self._extract_list(first.goals, "items"))
        second_goals = set(self._extract_list(second.goals, "items"))
        shared_goals = sorted(first_goals & second_goals)

        first_slots = set(self._extract_list(first.availability, "slots"))
        second_slots = set(self._extract_list(second.availability, "slots"))
        shared_slots = sorted(first_slots & second_slots)

        score = 0.0
        if shared_interests:
            score += len(shared_interests) * 2
        if shared_goals:
            score += len(shared_goals)
        if shared_slots:
            score += 1.5
        if first.company and second.company:
            if first.company.strip().lower() == second.company.strip().lower():
                score *= 0.8  # prefer diversity between companies
            else:
                score += 0.5

        rationale_parts: List[str] = []
        if shared_interests:
            rationale_parts.append(f"{len(shared_interests)} intérêts communs")
        if shared_goals:
            rationale_parts.append(f"{len(shared_goals)} objectifs alignés")
        if shared_slots:
            rationale_parts.append("disponibilités compatibles")
        if not rationale_parts:
            rationale_parts.append("complémentarité potentielle")

        metadata = {
            "shared_interests": shared_interests,
            "shared_goals": shared_goals,
            "shared_slots": shared_slots,
        }
        return score, ", ".join(rationale_parts), metadata

    def _extract_list(self, container: Any, key: str) -> List[str]:
        if isinstance(container, dict):
            value = container.get(key, [])
        else:
            value = container or []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _serialize_profile(self, profile: ParticipantProfile) -> Dict[str, Any]:
        return {
            "id": profile.id,
            "event_id": profile.event_id,
            "email": profile.attendee_email,
            "name": profile.attendee_name,
            "company": profile.company,
            "bio": profile.bio,
            "headline": profile.headline,
            "interests": self._extract_list(profile.interests, "items"),
            "goals": self._extract_list(profile.goals, "items"),
            "availability": self._extract_list(profile.availability, "slots"),
            "metadata": profile.metadata or {},
            "created_at": profile.created_at.isoformat(),
        }

    def _serialize_suggestion(self, suggestion) -> Dict[str, Any]:
        participant = suggestion.participant
        match = suggestion.suggested_participant
        return {
            "id": suggestion.id,
            "event_id": suggestion.event_id,
            "participant_email": participant.attendee_email if participant else None,
            "participant_name": participant.attendee_name if participant else None,
            "suggested_email": match.attendee_email if match else None,
            "suggested_name": match.attendee_name if match else None,
            "score": suggestion.score,
            "status": suggestion.status,
            "rationale": suggestion.rationale,
            "metadata": suggestion.metadata or {},
            "created_at": suggestion.created_at.isoformat(),
        }
