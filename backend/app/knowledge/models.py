"""The systems and document types that will feed Nexus.

    systems          where content lives: wikis, document sites, work tracking
    document types   what the content is: requirements, designs
    link groups      how the team groups its links today

The listing is the MUFG team's own (Swim Lane 1). `feeds` is Nexus's
proposal for what each would become in Nexus, not an agreed integration.
Nothing is connected in the prototype, and a value the owning team has not
confirmed is left blank rather than guessed.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

_ID = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

SystemKind = Literal["wiki", "document_site", "work_tracking", "service_management", "document_store"]
Connection = Literal["not_connected", "connected"]


class SourceSystem(BaseModel):
    id: str = Field(pattern=_ID)
    name: str
    kind: SystemKind
    # What it would feed in Nexus: a proposal.
    feeds: str
    # Blank until the owning team confirms them.
    owner: str = ""
    location: str = ""
    connection: Connection = "not_connected"


class DocumentType(BaseModel):
    id: str = Field(pattern=_ID)
    abbreviation: str
    # Blank where the team has not said what it stands for or covers.
    name: str = ""
    about: str = ""
    feeds: str = ""
    # The systems it is kept in, once the team confirms them.
    lives_in: list[str] = []
    owner: str = ""


class LinkGroup(BaseModel):
    id: str = Field(pattern=_ID)
    name: str
    systems: list[str]


class KnowledgeSources(BaseModel):
    systems: list[SourceSystem]
    document_types: list[DocumentType]
    link_groups: list[LinkGroup]

    @model_validator(mode="after")
    def consistent(self):
        system_ids = [s.id for s in self.systems]
        if len(set(system_ids)) != len(system_ids):
            raise ValueError("Duplicate source system id")
        document_ids = [d.id for d in self.document_types]
        if len(set(document_ids)) != len(document_ids):
            raise ValueError("Duplicate document type id")
        known = set(system_ids)
        for owner_id, ids in [
            *((d.id, d.lives_in) for d in self.document_types),
            *((g.id, g.systems) for g in self.link_groups),
        ]:
            unknown = sorted(set(ids) - known)
            if unknown:
                raise ValueError(f"{owner_id}: unknown system {unknown[0]}")
        return self
