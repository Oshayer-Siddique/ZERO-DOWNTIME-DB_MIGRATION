from pydantic import BaseModel, ConfigDict, field_validator


def normalize_name(value: str) -> str:
    return " ".join(value.split())


class LegacyUser(BaseModel):
    name: str


class LegacyUserInput(LegacyUser):
    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = normalize_name(value)
        if not value:
            raise ValueError("Name must not be blank.")
        return value


class ModernUser(BaseModel):
    first_name: str
    last_name: str


class ModernUserInput(ModernUser):
    model_config = ConfigDict(extra="forbid")

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_fields(cls, value: str) -> str:
        return normalize_name(value)

    @field_validator("first_name")
    @classmethod
    def require_first_name(cls, value: str) -> str:
        if not value:
            raise ValueError("First name must not be blank.")
        return value

