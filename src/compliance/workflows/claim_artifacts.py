"""Claim-artifact reads for analysis — the one home for filesystem I/O.

Policy stays filesystem-free: every claim-input read (texts, signature, HITL,
OCR-failure reason, preprocess run_id) goes through ``ClaimArtifactReader``.
The pipeline builds the reader on the appropriate root and passes results into
policy as arguments.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from compliance.config.settings import PreprocessedArtifactNames

__all__ = ["ClaimArtifactReader"]


@dataclass(frozen=True)
class ClaimArtifactReader:
    """Read preprocessed claim artifacts from one claim directory.

    :param claim_dir: Absolute path to the claim artifact folder.
    :param artifacts: Configured preprocessed artifact basenames.
    """

    claim_dir: Path
    artifacts: PreprocessedArtifactNames

    def texts(self) -> dict[str, str]:
        """Read description and supporting markdown from the claim folder.

        :return: Dict with description_text, supporting_document_text,
            supporting_documents_text (empty string when the optional
            supporting_documents file is absent).
        """
        supporting_documents_path = self.claim_dir / self.artifacts.supporting_documents
        supporting_documents_text = (
            supporting_documents_path.read_text(encoding="utf-8") if supporting_documents_path.is_file() else ""
        )
        return {
            "description_text": (self.claim_dir / self.artifacts.description).read_text(encoding="utf-8"),
            "supporting_document_text": (self.claim_dir / self.artifacts.supporting_document).read_text(
                encoding="utf-8"
            ),
            "supporting_documents_text": supporting_documents_text,
        }

    def has_signature(self) -> bool:
        """True when any document_metadata entry has ``has_signature`` true.

        :return: Signature flag aggregated across metadata entries.
        """
        return any(bool(entry.get("has_signature")) for entry in self._metadata_entries())

    def human_in_the_loop(self) -> bool:
        """True when any document_metadata entry already requires human review.

        :return: Preprocess HITL flag aggregated across metadata entries.
        """
        return any(bool(entry.get("human_in_the_loop")) for entry in self._metadata_entries())

    def ocr_failure_reason(self) -> str | None:
        """Return preprocess OCR-failure reason if any document was tagged.

        Precedence: ``ocr_read_failure`` then ``ocr_failure``.

        :return: Failure code when present; else None.
        """
        found: set[str] = set()
        for entry in self._metadata_entries():
            reasons = entry.get("failure_reasons")
            if not isinstance(reasons, list):
                continue
            for code in ("ocr_read_failure", "ocr_failure"):
                if code in reasons:
                    found.add(code)
        return next((code for code in ("ocr_read_failure", "ocr_failure") if code in found), None)

    def metadata_run_id(self) -> str | None:
        """Return the preprocess ``run_id`` stamped on document_metadata.json.

        :return: Run id string, or None when absent (pre-SR-005 trees) or
            metadata is missing/malformed.
        """
        raw = self._metadata_raw()
        if raw is None:
            return None
        value = raw.get("run_id")
        return value if isinstance(value, str) else None

    def _metadata_entries(self) -> list[dict[str, object]]:
        """Load document metadata entries for this claim folder.

        :return: List of metadata dicts (empty when missing/invalid).
        """
        raw = self._metadata_raw()
        documents = raw.get("documents") if raw else None
        if not isinstance(documents, list):
            return []
        return [entry for entry in documents if isinstance(entry, dict)]

    def _metadata_raw(self) -> dict[str, object] | None:
        """Parse document_metadata.json once; None for missing or non-dict content.

        :return: Parsed object, or None when missing/invalid.
        """
        path = self.claim_dir / self.artifacts.document_metadata
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
