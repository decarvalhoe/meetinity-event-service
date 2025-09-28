"""Service layer dedicated to event registrations and attendance tracking."""
from __future__ import annotations

import base64
import json
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional

import qrcode
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from src.database import get_session
from src.integrations.base import IntegrationError
from src.integrations.payment_service import PaymentServiceClient
from src.models import (
    AttendanceRecord,
    Event,
    NoShowPenalty,
    Registration,
    WaitlistEntry,
)

__all__ = [
    "RegistrationService",
    "RegistrationScheduler",
    "RegistrationError",
    "RegistrationClosedError",
    "DuplicateRegistrationError",
    "PenaltyActiveError",
    "CheckInError",
    "PaymentProcessingError",
]


class RegistrationError(Exception):
    """Base class for registration related exceptions."""


class RegistrationClosedError(RegistrationError):
    """Raised when registrations are closed for an event."""


class DuplicateRegistrationError(RegistrationError):
    """Raised when an attendee has already registered or is on the waitlist."""


class PenaltyActiveError(RegistrationError):
    """Raised when an attendee has an active no-show penalty."""


class CheckInError(RegistrationError):
    """Raised when a check-in request cannot be honoured."""


class PaymentProcessingError(RegistrationError):
    """Raised when an interaction with the payment service fails."""


class RegistrationService:
    """High level operations for managing registrations and attendance."""

    def __init__(
        self,
        session: Session,
        *,
        payment_client: Optional[PaymentServiceClient] = None,
    ) -> None:
        self.session = session
        self.payment_client = payment_client or PaymentServiceClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def open_registrations(self, event_id: int) -> Dict[str, Any]:
        event = self._get_event(event_id)
        event.registration_open = True
        self.session.commit()
        return self._serialize_event_state(event)

    def close_registrations(self, event_id: int) -> Dict[str, Any]:
        event = self._get_event(event_id)
        event.registration_open = False
        self.session.commit()
        return self._serialize_event_state(event)

    def register_attendee(
        self,
        event_id: int,
        *,
        email: str,
        full_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = self._get_event(event_id)
        self._ensure_registration_is_open(event)
        clean_email = self._normalize_email(email)

        if self._has_active_penalty(clean_email):
            raise PenaltyActiveError(
                "Le participant est temporairement bloqué suite à des absences répétées."
            )

        self._ensure_not_already_registered(event_id, clean_email)

        metadata_payload = dict(metadata or {})

        confirmed_count = self._count_confirmed_registrations(event_id)
        capacity = event.attendees if event.attendees is not None else 0

        if capacity == 0 or confirmed_count < capacity:
            registration = self._create_registration(
                event,
                email=clean_email,
                full_name=full_name,
                metadata=json.dumps(metadata_payload, sort_keys=True),
            )
            pricing = self._extract_pricing(event)
            if pricing:
                payment_metadata = self._capture_payment(
                    event,
                    registration,
                    pricing,
                    attendee_email=clean_email,
                    metadata=metadata_payload,
                )
                metadata_payload["payment"] = payment_metadata
                registration.metadata = json.dumps(metadata_payload, sort_keys=True)
                self.session.flush()
            self.session.commit()
            return {
                "status": "confirmed",
                "registration": self._serialize_registration(registration),
            }

        entry = self._create_waitlist_entry(
            event,
            email=clean_email,
            full_name=full_name,
        )
        self.session.commit()
        return {
            "status": "waitlisted",
            "waitlist_entry": self._serialize_waitlist_entry(entry),
        }

    def cancel_registration(self, event_id: int, registration_id: int) -> Dict[str, Any]:
        registration = self._get_registration(event_id, registration_id)
        if registration.status in {"cancelled", "no_show"}:
            return {"status": registration.status}

        metadata_payload = self._metadata_as_dict(registration.metadata)
        payment_info = metadata_payload.get("payment")

        registration.status = "cancelled"
        self.session.flush()
        if payment_info and payment_info.get("status") == "captured":
            updated_payment = self._refund_payment(
                registration.event,
                payment_info,
            )
            metadata_payload["payment"] = updated_payment
            registration.metadata = json.dumps(metadata_payload, sort_keys=True)
            self.session.flush()
        promoted = self._promote_waitlist_if_possible(registration.event)
        self.session.commit()
        payload: Dict[str, Any] = {"status": "cancelled"}
        if promoted:
            payload["promoted"] = [self._serialize_registration(item) for item in promoted]
        return payload

    def list_registrations(self, event_id: int) -> List[Dict[str, Any]]:
        event = self._get_event(event_id)
        return [self._serialize_registration(reg) for reg in event.registrations]

    def list_waitlist(self, event_id: int) -> List[Dict[str, Any]]:
        event = self._get_event(event_id)
        return [self._serialize_waitlist_entry(entry) for entry in event.waitlist_entries]

    def list_attendance(self, event_id: int) -> List[Dict[str, Any]]:
        event = self._get_event(event_id)
        data: List[Dict[str, Any]] = []
        for registration in event.registrations:
            data.append(self._serialize_attendance(registration))
        return data

    def trigger_waitlist_promotion(self, event_id: int) -> List[Dict[str, Any]]:
        event = self._get_event(event_id)
        promoted = self._promote_waitlist_if_possible(event)
        self.session.commit()
        return [self._serialize_registration(item) for item in promoted]

    def check_in_attendee(
        self, token: str, *, method: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        registration = self._get_registration_by_token(token)
        if registration.status == "cancelled":
            raise CheckInError("Cette inscription a été annulée.")
        if registration.status == "no_show":
            raise CheckInError("Le participant a été marqué comme absent.")
        if registration.status == "checked_in":
            return self._serialize_attendance(registration)

        record = registration.attendance_record
        if record is None:
            record = AttendanceRecord(registration=registration)
            self.session.add(record)

        record.check_in_time = datetime.utcnow()
        record.check_in_method = method or "qr"
        record.scan_payload = json.dumps(metadata or {}, sort_keys=True)
        registration.status = "checked_in"
        self.session.commit()
        return self._serialize_attendance(registration)

    def detect_no_shows(self, event_id: int, *, current_date: Optional[date] = None) -> Dict[str, Any]:
        event = self._get_event(event_id)
        today = current_date or date.today()
        if event.event_date >= today:
            return {"penalized": []}

        penalized: List[Dict[str, Any]] = []
        expiry = datetime.combine(event.event_date, datetime.min.time()) + timedelta(days=30)

        for registration in event.registrations:
            if registration.status in {"confirmed"} and registration.attendance_record is None:
                registration.status = "no_show"
                penalty = NoShowPenalty(
                    attendee_email=registration.attendee_email,
                    event=event,
                    reason="Absence non signalée",
                    expires_at=expiry,
                )
                self.session.add(penalty)
                penalized.append(
                    {
                        "email": registration.attendee_email,
                        "expires_at": penalty.expires_at.isoformat() if penalty.expires_at else None,
                    }
                )

        self.session.commit()
        return {"penalized": penalized}

    def send_reminders(self, within_days: int = 3) -> List[Dict[str, Any]]:
        threshold = date.today() + timedelta(days=within_days)
        query = (
            select(Event)
            .where(Event.event_date <= threshold)
            .where(Event.event_date >= date.today())
            .where(Event.registration_open.is_(True))
        )
        events = self.session.scalars(query).all()
        reminders: List[Dict[str, Any]] = []
        for event in events:
            for registration in event.registrations:
                if registration.status == "confirmed":
                    reminders.append(
                        {
                            "event_id": event.id,
                            "email": registration.attendee_email,
                            "event_date": event.event_date.isoformat(),
                        }
                    )
        return reminders

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_event(self, event_id: int) -> Event:
        event = self.session.get(Event, event_id)
        if event is None:
            raise LookupError(f"Event {event_id} not found")
        return event

    def _ensure_registration_is_open(self, event: Event) -> None:
        if not event.registration_open:
            raise RegistrationClosedError("Les inscriptions sont actuellement fermées.")
        if event.registration_deadline and event.registration_deadline < datetime.utcnow():
            raise RegistrationClosedError("La période d'inscription est terminée.")

    def _has_active_penalty(self, email: str) -> bool:
        now = datetime.utcnow()
        query = (
            select(NoShowPenalty)
            .where(NoShowPenalty.attendee_email == email)
            .where((NoShowPenalty.expires_at.is_(None)) | (NoShowPenalty.expires_at > now))
        )
        return self.session.scalars(query).first() is not None

    def _ensure_not_already_registered(self, event_id: int, email: str) -> None:
        reg_query = (
            select(Registration)
            .where(Registration.event_id == event_id)
            .where(Registration.attendee_email == email)
            .where(Registration.status != "cancelled")
        )
        if self.session.scalars(reg_query).first():
            raise DuplicateRegistrationError("Le participant est déjà inscrit à l'événement.")

        waitlist_query = (
            select(WaitlistEntry)
            .where(WaitlistEntry.event_id == event_id)
            .where(WaitlistEntry.attendee_email == email)
        )
        if self.session.scalars(waitlist_query).first():
            raise DuplicateRegistrationError(
                "Le participant figure déjà sur la liste d'attente."
            )

    def _count_confirmed_registrations(self, event_id: int) -> int:
        query = (
            select(func.count())
            .select_from(Registration)
            .where(Registration.event_id == event_id)
            .where(Registration.status.in_(["confirmed", "checked_in"]))
        )
        return int(self.session.execute(query).scalar_one())

    def _create_registration(
        self,
        event: Event,
        *,
        email: str,
        full_name: Optional[str],
        metadata: Optional[str],
    ) -> Registration:
        token = uuid.uuid4().hex
        qr_code = self._build_qr_code(token)
        registration = Registration(
            event=event,
            attendee_email=email,
            attendee_name=full_name,
            metadata=metadata,
            check_in_token=token,
            qr_code_data=qr_code,
        )
        self.session.add(registration)
        self.session.flush()
        self.session.refresh(registration)
        return registration

    def _create_waitlist_entry(
        self,
        event: Event,
        *,
        email: str,
        full_name: Optional[str],
    ) -> WaitlistEntry:
        entry = WaitlistEntry(
            event=event,
            attendee_email=email,
            attendee_name=full_name,
        )
        self.session.add(entry)
        self.session.flush()
        self.session.refresh(entry)
        return entry

    @staticmethod
    def _metadata_as_dict(metadata: Optional[str]) -> Dict[str, Any]:
        if not metadata:
            return {}
        try:
            payload = json.loads(metadata)
        except (TypeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _extract_pricing(event: Event) -> Optional[Dict[str, Any]]:
        settings = event.settings if isinstance(event.settings, dict) else {}
        pricing = settings.get("pricing") if isinstance(settings, dict) else None
        if not isinstance(pricing, dict):
            return None
        amount = pricing.get("amount")
        currency = pricing.get("currency", "EUR")
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            return None
        if amount_value <= 0:
            return None
        currency_value = str(currency or "EUR").upper()
        return {"amount": amount_value, "currency": currency_value}

    def _capture_payment(
        self,
        event: Event,
        registration: Registration,
        pricing: Dict[str, Any],
        *,
        attendee_email: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.payment_client is None:  # pragma: no cover - guardrail
            raise PaymentProcessingError("Service de paiement indisponible.")
        enriched_metadata = dict(metadata)
        enriched_metadata.update(
            {
                "registration_id": registration.id,
                "event_title": event.title,
            }
        )
        try:
            response = self.payment_client.capture_payment(
                event_id=event.id,
                attendee_email=attendee_email,
                amount=pricing["amount"],
                currency=pricing["currency"],
                metadata=enriched_metadata,
            )
        except IntegrationError as exc:
            self.session.rollback()
            raise PaymentProcessingError(
                "Le paiement a échoué. Aucune inscription confirmée."
            ) from exc
        payment_payload = response.get("payment", response)
        payment_id = payment_payload.get("id") or payment_payload.get("payment_id")
        status = payment_payload.get("status", "captured")
        return {
            "id": payment_id,
            "status": status,
            "amount": pricing["amount"],
            "currency": pricing["currency"],
        }

    def _refund_payment(
        self,
        event: Event,
        payment_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.payment_client is None:  # pragma: no cover - guardrail
            raise PaymentProcessingError("Service de paiement indisponible.")
        payment_id = payment_info.get("id")
        if not payment_id:
            return payment_info
        try:
            response = self.payment_client.refund_payment(
                payment_id,
                reason=f"Annulation inscription événement {event.id}",
            )
        except IntegrationError as exc:
            self.session.rollback()
            raise PaymentProcessingError(
                "Le remboursement a échoué. Statut de l'inscription inchangé."
            ) from exc
        updated = dict(payment_info)
        updated["status"] = response.get("status", "refunded")
        if "refund" in response:
            updated["refund"] = response["refund"]
        else:
            updated["refund"] = response
        return updated

    def _promote_waitlist_if_possible(self, event: Event) -> List[Registration]:
        capacity = event.attendees if event.attendees is not None else 0
        if capacity == 0:
            return []
        confirmed = self._count_confirmed_registrations(event.id)
        available = max(capacity - confirmed, 0)
        if available <= 0:
            return []

        query = (
            select(WaitlistEntry)
            .where(WaitlistEntry.event_id == event.id)
            .order_by(WaitlistEntry.created_at.asc())
            .limit(available)
        )
        entries: Iterable[WaitlistEntry] = self.session.scalars(query).all()
        promoted: List[Registration] = []
        pricing = self._extract_pricing(event)
        for entry in entries:
            metadata_payload: Dict[str, Any] = {}
            registration = self._create_registration(
                event,
                email=entry.attendee_email,
                full_name=entry.attendee_name,
                metadata=json.dumps(metadata_payload, sort_keys=True),
            )
            if pricing:
                payment_metadata = self._capture_payment(
                    event,
                    registration,
                    pricing,
                    attendee_email=entry.attendee_email,
                    metadata=metadata_payload,
                )
                metadata_payload["payment"] = payment_metadata
                registration.metadata = json.dumps(metadata_payload, sort_keys=True)
                self.session.flush()
            self.session.delete(entry)
            promoted.append(registration)
        return promoted

    def _get_registration(self, event_id: int, registration_id: int) -> Registration:
        query = (
            select(Registration)
            .where(Registration.id == registration_id)
            .where(Registration.event_id == event_id)
        )
        try:
            return self.session.execute(query).scalar_one()
        except NoResultFound as exc:
            raise LookupError(
                f"Registration {registration_id} for event {event_id} not found"
            ) from exc

    def _get_registration_by_token(self, token: str) -> Registration:
        query = select(Registration).where(Registration.check_in_token == token)
        try:
            return self.session.execute(query).scalar_one()
        except NoResultFound as exc:
            raise CheckInError("Token de check-in invalide.") from exc

    @staticmethod
    def _normalize_email(email: str) -> str:
        if not isinstance(email, str) or not email.strip():
            raise ValueError("Adresse e-mail invalide.")
        return email.strip().casefold()

    @staticmethod
    def _build_qr_code(token: str) -> str:
        qr = qrcode.QRCode(version=1, box_size=5, border=2)
        qr.add_data(token)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def _serialize_event_state(self, event: Event) -> Dict[str, Any]:
        return {
            "event_id": event.id,
            "registration_open": event.registration_open,
            "registration_deadline": event.registration_deadline.isoformat()
            if event.registration_deadline
            else None,
        }

    def _serialize_registration(self, registration: Registration) -> Dict[str, Any]:
        metadata_payload = self._metadata_as_dict(registration.metadata)
        payment_info = metadata_payload.get("payment")
        payload = {
            "id": registration.id,
            "event_id": registration.event_id,
            "email": registration.attendee_email,
            "name": registration.attendee_name,
            "status": registration.status,
            "qr_code": registration.qr_code_data,
            "token": registration.check_in_token,
            "created_at": registration.created_at.isoformat(),
        }
        if isinstance(payment_info, dict):
            payload["payment"] = {
                "id": payment_info.get("id"),
                "status": payment_info.get("status"),
                "amount": payment_info.get("amount"),
                "currency": payment_info.get("currency"),
            }
        return payload

    def _serialize_waitlist_entry(self, entry: WaitlistEntry) -> Dict[str, Any]:
        return {
            "id": entry.id,
            "event_id": entry.event_id,
            "email": entry.attendee_email,
            "name": entry.attendee_name,
            "created_at": entry.created_at.isoformat(),
        }

    def _serialize_attendance(self, registration: Registration) -> Dict[str, Any]:
        record = registration.attendance_record
        return {
            "registration_id": registration.id,
            "email": registration.attendee_email,
            "status": registration.status,
            "checked_in_at": record.check_in_time.isoformat() if record and record.check_in_time else None,
            "method": record.check_in_method if record else None,
        }


class RegistrationScheduler:
     """Lightweight scheduler for reminder and waitlist jobs."""

     def __init__(self) -> None:
         self._scheduler = BackgroundScheduler(timezone="UTC")
         self._started = False

     def start(self) -> None:
         if self._started:
             return
         self._scheduler.add_job(self._reminder_job, "interval", hours=24)
         self._scheduler.add_job(self._waitlist_job, "interval", minutes=30)
         self._scheduler.start()
         self._started = True

     def shutdown(self) -> None:
         if self._started:
             self._scheduler.shutdown()
             self._started = False

     def _reminder_job(self) -> None:
        session = get_session()
        try:
            service = RegistrationService(session)
            service.send_reminders()
        finally:
            session.close()

     def _waitlist_job(self) -> None:
         session = get_session()
         try:
             service = RegistrationService(session)
             query = select(Event.id).where(Event.registration_open.is_(True))
             for event_id in session.scalars(query).all():
                 service.trigger_waitlist_promotion(event_id)
         finally:
             session.close()
