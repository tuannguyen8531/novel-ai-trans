"""Validated output from the translation-memory learner."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LearnedCharacter(BaseModel):
    model_config = ConfigDict(strict=True)

    translated_name: str = ""
    role: str = ""
    pronoun: str = ""


class LearnedCharacters(BaseModel):
    model_config = ConfigDict(strict=True)

    entities: dict[str, LearnedCharacter]
    edges: list[list[str | int]] = Field(default_factory=list)

    @field_validator("edges")
    @classmethod
    def validate_edges(cls, edges: list[list[str | int]]) -> list[list[str | int]]:
        for edge in edges:
            if len(edge) < 3 or any(not isinstance(value, str) for value in edge[:3]):
                raise ValueError("Each relationship needs two source names and a string relationship type.")
            if any(not isinstance(value, int) for value in edge[3:]):
                raise ValueError("Relationship chapter markers must be integers.")
        return edges


class LearningResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    terms: dict[str, str]
    characters: LearnedCharacters
    translated_title_base: str = ""
