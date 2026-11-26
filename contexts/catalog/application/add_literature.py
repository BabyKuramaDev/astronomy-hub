"""Use case: add-literature. Records a source the Librarian found, in catalog.json.

Same pattern as select-peak: the agent decides what is relevant; the tool validates
and writes. A URL already recorded is not added twice.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from shared.contracts import CatalogFile, LiteratureRef
from shared.toolkit.dossier import Dossier
from shared.toolkit.errors import InvalidInputError
from shared.toolkit.meta import ToolMeta

CATALOG = "catalog.json"


@dataclass
class AddLiterature:
    dossier: Dossier
    meta: ToolMeta

    def execute(self, title: str, url: str, note: str) -> dict[str, Any]:
        if not self.dossier.exists(CATALOG):
            raise InvalidInputError("catalog.json not found: run crossmatch first")
        try:
            ref = LiteratureRef(title=title.strip(), url=url.strip(), note=note.strip())  # type: ignore[arg-type]
        except ValidationError as exc:
            raise InvalidInputError(f"invalid reference: {exc.errors()[0]['msg']}") from exc
        current = self.dossier.read_envelope(CATALOG, CatalogFile)
        known = {str(r.url) for r in current.data.literature}
        added = str(ref.url) not in known
        if added:
            data = current.data.model_copy(update={"literature": [*current.data.literature, ref]})
            # Keep the inputs crossmatch recorded (signal.json): later tools check them.
            self.dossier.write_envelope(CATALOG, self.meta.envelope(data, current.inputs))
        return {
            "tic_id": self.meta.tic_id,
            "added": added,
            "url": str(ref.url),
            "n_literature": len(current.data.literature) + int(added),
            "file": CATALOG,
        }
