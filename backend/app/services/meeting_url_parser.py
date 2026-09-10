"""
Meeting URL Parser & Validation Subsystem
Provides robust, provider-specific parsing, URL normalization, thread ID extraction,
and structured error code validation for Google Meet and Microsoft Teams URLs.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from app.core.exceptions import BadRequestException


@dataclass
class ParsedMeetingURL:
    """Standardized result of parsing a meeting URL."""
    provider: str
    external_meeting_id: str
    canonical_url: str
    conference_code: Optional[str] = None
    thread_id: Optional[str] = None
    message_id: Optional[str] = None
    tenant_id: Optional[str] = None
    organizer_id: Optional[str] = None
    raw_query_params: Optional[Dict[str, Any]] = None


class MeetingURLParser:
    """Validates and parses provider meeting URLs into structured identifiers."""

    # Regex for Google Meet: 3-4-3 letters (e.g., abc-defg-hij) or spaces/UUID/custom code
    GOOGLE_MEET_CODE_REGEX = re.compile(r"^[a-z]{3}-[a-z]{4}-[a-z]{3}$", re.IGNORECASE)
    GOOGLE_MEET_SPACE_REGEX = re.compile(r"^spaces/([a-zA-Z0-9_-]+)$")

    @classmethod
    def parse(cls, url_or_code: str, expected_provider: Optional[str] = None) -> ParsedMeetingURL:
        """
        Parses a URL or meeting code and returns normalized ParsedMeetingURL.
        Raises BadRequestException with structured error codes on failure.
        """
        if not url_or_code or not url_or_code.strip():
            raise BadRequestException(
                message="Meeting URL or conference code cannot be empty",
                code="INVALID_MEETING_URL",
            )

        trimmed = url_or_code.strip()

        # Check if direct Google Meet code or space name
        if cls.GOOGLE_MEET_CODE_REGEX.match(trimmed):
            code = trimmed.lower()
            return ParsedMeetingURL(
                provider="google_meet",
                external_meeting_id=code,
                canonical_url=f"https://meet.google.com/{code}",
                conference_code=code,
            )

        space_match = cls.GOOGLE_MEET_SPACE_REGEX.match(trimmed)
        if space_match:
            space_id = space_match.group(1)
            return ParsedMeetingURL(
                provider="google_meet",
                external_meeting_id=space_id,
                canonical_url=f"https://meet.google.com/{space_id}",
                conference_code=space_id,
            )

        # Parse URL
        if not (trimmed.startswith("http://") or trimmed.startswith("https://")):
            # Could be domain-prefixed e.g. "meet.google.com/xxx-yyyy-zzz"
            if trimmed.startswith("meet.google.com/") or trimmed.startswith("teams.microsoft.com/"):
                trimmed = f"https://{trimmed}"
            else:
                raise BadRequestException(
                    message=f"Invalid meeting URL scheme or format: '{url_or_code}'",
                    code="INVALID_MEETING_URL",
                )

        try:
            parsed = urlparse(trimmed)
        except Exception as exc:
            raise BadRequestException(
                message=f"Failed to parse URL syntax: {str(exc)}",
                code="INVALID_MEETING_URL",
            )

        hostname = (parsed.hostname or "").lower()

        # ---------------------------------------------------------------------
        # Google Meet Domain Parser
        # ---------------------------------------------------------------------
        if "meet.google.com" in hostname:
            if expected_provider and expected_provider.lower() not in {"google_meet", "google-meet", "meet"}:
                raise BadRequestException(
                    message=f"URL '{url_or_code}' is for Google Meet, but expected provider '{expected_provider}'",
                    code="UNSUPPORTED_PROVIDER",
                )
            
            path = parsed.path.strip("/")
            if not path:
                raise BadRequestException(
                    message="Google Meet URL is missing conference code (path is empty)",
                    code="INVALID_MEETING_URL",
                )
            
            # Format: /xxx-yyyy-zzz or /_meet/xxx-yyyy-zzz
            parts = path.split("/")
            code_candidate = parts[-1].strip().lower()

            # Clean query parameters or anchors if in path
            code_candidate = code_candidate.split("?")[0].split("#")[0]

            if not (cls.GOOGLE_MEET_CODE_REGEX.match(code_candidate) or re.match(r"^[a-zA-Z0-9_-]{8,36}$", code_candidate)):
                raise BadRequestException(
                    message=f"Malformed Google Meet conference code '{code_candidate}' in URL '{url_or_code}'",
                    code="INVALID_MEETING_URL",
                )

            return ParsedMeetingURL(
                provider="google_meet",
                external_meeting_id=code_candidate,
                canonical_url=f"https://meet.google.com/{code_candidate}",
                conference_code=code_candidate,
                raw_query_params=parse_qs(parsed.query),
            )

        # ---------------------------------------------------------------------
        # Microsoft Teams Domain Parser
        # ---------------------------------------------------------------------
        elif "teams.microsoft.com" in hostname or "teams.live.com" in hostname:
            if expected_provider and expected_provider.lower() not in {"teams", "microsoft_teams", "microsoft-teams"}:
                raise BadRequestException(
                    message=f"URL '{url_or_code}' is for Microsoft Teams, but expected provider '{expected_provider}'",
                    code="UNSUPPORTED_PROVIDER",
                )

            path = unquote(parsed.path)
            query_params = parse_qs(parsed.query)

            # Match standard /l/meetup-join/<threadId>/<messageId>
            meetup_match = re.search(r"/l/meetup-join/([^/?#]+)(?:/(\d+))?", path)
            if meetup_match:
                thread_id = meetup_match.group(1)
                message_id = meetup_match.group(2)
                
                # Context json parameter
                context_str = query_params.get("context", [None])[0]
                tenant_id = None
                organizer_id = None
                if context_str:
                    try:
                        import json
                        ctx_json = json.loads(context_str)
                        tenant_id = ctx_json.get("Tid")
                        organizer_id = ctx_json.get("Oid")
                    except Exception:
                        pass

                return ParsedMeetingURL(
                    provider="teams",
                    external_meeting_id=thread_id,
                    canonical_url=trimmed,
                    thread_id=thread_id,
                    message_id=message_id,
                    tenant_id=tenant_id,
                    organizer_id=organizer_id,
                    raw_query_params=query_params,
                )

            # Fallback for /meet/<meetingCode>
            meet_match = re.search(r"/meet/([^/?#]+)", path)
            if meet_match:
                meet_code = meet_match.group(1)
                return ParsedMeetingURL(
                    provider="teams",
                    external_meeting_id=meet_code,
                    canonical_url=trimmed,
                    thread_id=meet_code,
                    raw_query_params=query_params,
                )

            raise BadRequestException(
                message=f"Unrecognized Microsoft Teams URL structure: '{url_or_code}'",
                code="INVALID_MEETING_URL",
            )

        # ---------------------------------------------------------------------
        # Unsupported Provider / Domain
        # ---------------------------------------------------------------------
        else:
            raise BadRequestException(
                message=f"Unsupported meeting platform URL domain '{hostname}'. Supported: Google Meet (meet.google.com), Microsoft Teams (teams.microsoft.com)",
                code="UNSUPPORTED_PROVIDER",
            )


def parse_and_validate_meeting_url(url: str, provider: Optional[str] = None) -> ParsedMeetingURL:
    """Convenience helper to parse and validate meeting URL."""
    return MeetingURLParser.parse(url, expected_provider=provider)
