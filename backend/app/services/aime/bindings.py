"""Typed AMIE packet bindings for ingestion."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class PacketBindingError(Exception):
    """Raised when packet payload cannot be bound to a known schema."""


class UnsupportedPacketType(PacketBindingError):
    """Raised when packet type is unsupported by this service."""


class AMIEPacketHeaderBinding(BaseModel):
    """Common AMIE packet header."""

    packet_rec_id: int
    trans_rec_id: int | None = None
    packet_id: int | None = None
    transaction_id: int | None = None
    local_site_name: str | None = None
    remote_site_name: str | None = None
    originating_site_name: str | None = None
    outgoing_flag: bool | None = None
    transaction_state: str | None = None
    packet_state: str | None = None
    packet_timestamp: datetime | None = None
    client_state: str | None = None

    model_config = ConfigDict(extra="ignore")


class RequestProjectCreateBodyBinding(BaseModel):
    """Body fields for ``request_project_create``."""

    AllocationType: str
    EndDate: datetime | date
    GrantNumber: str
    PfosNumber: str
    PiFirstName: str
    PiLastName: str
    PiOrganization: str
    PiOrgCode: str
    StartDate: datetime | date
    ResourceList: list[str]
    RecordID: str | int | None
    ServiceUnitsAllocated: str | int | float

    Abstract: str | None = None
    BoardType: str | None = None
    PiBusinessPhoneNumber: str | None = None
    PiBusinessPhoneExtension: str | None = None
    PiCity: str | None = None
    PiCountry: str | None = None
    PiDepartment: str | None = None
    PiDnList: list[str] = Field(default_factory=list)
    PiEmail: str | None = None
    PiMiddleName: str | None = None
    PiPersonID: str | None = None
    NsfStatusCode: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NsfStatusCode", "PiNsfStatusCode"),
    )
    PiRequestedLoginList: list[str] = Field(default_factory=list)
    PiState: str | None = None
    PiStreetAddress: str | None = None
    PiStreetAddress2: str | None = None
    PiZip: str | None = None
    ProjectID: str | None = None
    ProjectTitle: str | None = None
    RequestType: str | None = None
    RoleList: list[str] = Field(default_factory=list)
    SitePersonId: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

    @field_validator("ResourceList")
    @classmethod
    def validate_single_resource(cls, value: list[str]) -> list[str]:
        """AMIE request_project_create packets must contain one resource."""
        if len(value) != 1:
            raise ValueError("ResourceList must contain exactly one entry")
        return value


class RequestAccountCreateBodyBinding(BaseModel):
    """Body fields for ``request_account_create``."""

    GrantNumber: str
    ResourceList: list[str]
    UserFirstName: str
    UserLastName: str
    UserOrganization: str
    UserOrgCode: str

    AllocatedResource: str | None = None
    NsfStatusCode: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NsfStatusCode", "UserNsfStatusCode"),
    )
    ProjectID: str | None = None
    RoleList: list[str] = Field(default_factory=list)
    SitePersonId: list[dict[str, Any]] = Field(default_factory=list)
    UserBusinessPhoneNumber: str | None = None
    UserBusinessPhoneExtension: str | None = None
    UserCity: str | None = None
    UserCountry: str | None = None
    UserDepartment: str | None = None
    UserDnList: list[str] = Field(default_factory=list)
    UserEmail: str | None = None
    UserGlobalID: str | None = None
    UserMiddleName: str | None = None
    UserPersonID: str | None = None
    UserRemoteSiteLogin: str | None = None
    UserRequestedLoginList: list[str] = Field(default_factory=list)
    UserState: str | None = None
    UserStreetAddress: str | None = None
    UserStreetAddress2: str | None = None
    UserTitle: str | None = None
    UserZip: str | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("ResourceList")
    @classmethod
    def validate_single_resource(cls, value: list[str]) -> list[str]:
        """AMIE request_account_create packets must contain one resource."""
        if len(value) != 1:
            raise ValueError("ResourceList must contain exactly one entry")
        return value


class DataProjectCreateBodyBinding(BaseModel):
    """Body fields for ``data_project_create``."""

    PersonID: str
    ProjectID: str
    DnList: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class DataAccountCreateBodyBinding(BaseModel):
    """Body fields for ``data_account_create``."""

    PersonID: str
    ProjectID: str
    DnList: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class RequestUserModifyBodyBinding(BaseModel):
    """Body fields for ``request_user_modify``."""

    ActionType: str = Field(validation_alias=AliasChoices("ActionType", "Actiontype"))
    PersonID: str

    AcademicDegree: str | None = None
    BusinessPhoneComment: str | None = None
    BusinessPhoneExtension: str | None = None
    BusinessPhoneNumber: str | None = None
    City: str | None = None
    Country: str | None = None
    Department: str | None = None
    DnList: list[str] = Field(default_factory=list)
    Email: str | None = None
    Fax: str | None = None
    FirstName: str | None = None
    HomePhoneComment: str | None = None
    HomePhoneExtension: str | None = None
    HomePhoneNumber: str | None = None
    LastName: str | None = None
    MiddleName: str | None = None
    NsfStatusCode: str | None = None
    Organization: str | None = None
    OrgCode: str | None = None
    State: str | None = None
    StreetAddress: str | None = None
    StreetAddress2: str | None = None
    Title: str | None = None
    Zip: str | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("ActionType")
    @classmethod
    def validate_action_type(cls, value: str) -> str:
        action = value.lower().strip()
        if action not in {"add", "delete", "replace"}:
            raise ValueError("ActionType must be one of add, delete, or replace")
        return action


class RequestPersonMergeBodyBinding(BaseModel):
    """Body fields for ``request_person_merge``."""

    KeepGlobalID: str | None = None
    KeepPersonID: str
    DeleteGlobalID: str | None = None
    DeletePersonID: str
    DeletePortalLogin: str | None = None
    KeepPortalLogin: str | None = None

    model_config = ConfigDict(extra="allow")


class RequestProjectInactivateBodyBinding(BaseModel):
    """Body fields for ``request_project_inactivate``."""

    ProjectID: str
    ResourceList: list[str]

    Comment: str | None = None
    AllocatedResource: str | None = None
    GrantNumber: str | None = None
    StartDate: datetime | date | None = None
    EndDate: datetime | date | None = None
    ServiceUnitsAllocated: str | int | float | None = None
    ServiceUnitsRemaining: str | int | float | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("ResourceList")
    @classmethod
    def validate_single_resource(cls, value: list[str]) -> list[str]:
        """AMIE inactivate/reactivate packets must contain one resource."""
        if len(value) != 1:
            raise ValueError("ResourceList must contain exactly one entry")
        return value


class RequestProjectReactivateBodyBinding(BaseModel):
    """Body fields for ``request_project_reactivate``."""

    ProjectID: str
    ResourceList: list[str]

    PersonID: str | None = None
    Comment: str | None = None
    AllocatedResource: str | None = None
    GrantNumber: str | None = None
    StartDate: datetime | date | None = None
    EndDate: datetime | date | None = None
    ServiceUnitsAllocated: str | int | float | None = None
    ServiceUnitsRemaining: str | int | float | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("ResourceList")
    @classmethod
    def validate_single_resource(cls, value: list[str]) -> list[str]:
        """AMIE inactivate/reactivate packets must contain one resource."""
        if len(value) != 1:
            raise ValueError("ResourceList must contain exactly one entry")
        return value


class RequestAccountInactivateBodyBinding(BaseModel):
    """Body fields for ``request_account_inactivate``."""

    PersonID: str
    ProjectID: str
    ResourceList: list[str]
    Comment: str | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("ResourceList")
    @classmethod
    def validate_single_resource(cls, value: list[str]) -> list[str]:
        """AMIE inactivate/reactivate packets must contain one resource."""
        if len(value) != 1:
            raise ValueError("ResourceList must contain exactly one entry")
        return value


class RequestAccountReactivateBodyBinding(BaseModel):
    """Body fields for ``request_account_reactivate``."""

    PersonID: str
    ProjectID: str
    ResourceList: list[str]
    Comment: str | None = None

    model_config = ConfigDict(extra="allow")

    @field_validator("ResourceList")
    @classmethod
    def validate_single_resource(cls, value: list[str]) -> list[str]:
        """AMIE inactivate/reactivate packets must contain one resource."""
        if len(value) != 1:
            raise ValueError("ResourceList must contain exactly one entry")
        return value


class InformTransactionCompleteBodyBinding(BaseModel):
    """Body fields for ``inform_transaction_complete``."""

    DetailCode: str | int
    Message: str
    StatusCode: str

    model_config = ConfigDict(extra="allow")


class RequestProjectCreatePacketBinding(BaseModel):
    """Typed wrapper for allocation packets."""

    type: Literal["request_project_create"]
    header: AMIEPacketHeaderBinding
    body: RequestProjectCreateBodyBinding

    model_config = ConfigDict(extra="ignore")


class RequestAccountCreatePacketBinding(BaseModel):
    """Typed wrapper for new-user packets."""

    type: Literal["request_account_create"]
    header: AMIEPacketHeaderBinding
    body: RequestAccountCreateBodyBinding

    model_config = ConfigDict(extra="ignore")


class DataProjectCreatePacketBinding(BaseModel):
    """Typed wrapper for ``data_project_create`` packets."""

    type: Literal["data_project_create"]
    header: AMIEPacketHeaderBinding
    body: DataProjectCreateBodyBinding

    model_config = ConfigDict(extra="ignore")


class DataAccountCreatePacketBinding(BaseModel):
    """Typed wrapper for ``data_account_create`` packets."""

    type: Literal["data_account_create"]
    header: AMIEPacketHeaderBinding
    body: DataAccountCreateBodyBinding

    model_config = ConfigDict(extra="ignore")


class RequestUserModifyPacketBinding(BaseModel):
    """Typed wrapper for ``request_user_modify`` packets."""

    type: Literal["request_user_modify"]
    header: AMIEPacketHeaderBinding
    body: RequestUserModifyBodyBinding

    model_config = ConfigDict(extra="ignore")


class RequestPersonMergePacketBinding(BaseModel):
    """Typed wrapper for ``request_person_merge`` packets."""

    type: Literal["request_person_merge"]
    header: AMIEPacketHeaderBinding
    body: RequestPersonMergeBodyBinding

    model_config = ConfigDict(extra="ignore")


class RequestProjectInactivatePacketBinding(BaseModel):
    """Typed wrapper for ``request_project_inactivate`` packets."""

    type: Literal["request_project_inactivate"]
    header: AMIEPacketHeaderBinding
    body: RequestProjectInactivateBodyBinding

    model_config = ConfigDict(extra="ignore")


class RequestProjectReactivatePacketBinding(BaseModel):
    """Typed wrapper for ``request_project_reactivate`` packets."""

    type: Literal["request_project_reactivate"]
    header: AMIEPacketHeaderBinding
    body: RequestProjectReactivateBodyBinding

    model_config = ConfigDict(extra="ignore")


class RequestAccountInactivatePacketBinding(BaseModel):
    """Typed wrapper for ``request_account_inactivate`` packets."""

    type: Literal["request_account_inactivate"]
    header: AMIEPacketHeaderBinding
    body: RequestAccountInactivateBodyBinding

    model_config = ConfigDict(extra="ignore")


class RequestAccountReactivatePacketBinding(BaseModel):
    """Typed wrapper for ``request_account_reactivate`` packets."""

    type: Literal["request_account_reactivate"]
    header: AMIEPacketHeaderBinding
    body: RequestAccountReactivateBodyBinding

    model_config = ConfigDict(extra="ignore")


class InformTransactionCompletePacketBinding(BaseModel):
    """Typed wrapper for ``inform_transaction_complete`` packets."""

    type: Literal["inform_transaction_complete"]
    header: AMIEPacketHeaderBinding
    body: InformTransactionCompleteBodyBinding

    model_config = ConfigDict(extra="ignore")


AMIESupportedPacketBinding = (
    RequestProjectCreatePacketBinding
    | RequestAccountCreatePacketBinding
    | DataProjectCreatePacketBinding
    | DataAccountCreatePacketBinding
    | RequestUserModifyPacketBinding
    | RequestPersonMergePacketBinding
    | RequestProjectInactivatePacketBinding
    | RequestProjectReactivatePacketBinding
    | RequestAccountInactivatePacketBinding
    | RequestAccountReactivatePacketBinding
    | InformTransactionCompletePacketBinding
)


def coerce_packet_dict(packet: dict[str, Any] | Any) -> dict[str, Any]:
    """Convert an amieclient packet object (or dict) to dict form."""
    if isinstance(packet, dict):
        return packet
    if hasattr(packet, "as_dict"):
        return packet.as_dict()
    raise PacketBindingError(f"Unsupported packet payload type: {type(packet)!r}")


def bind_packet(packet: dict[str, Any] | Any) -> AMIESupportedPacketBinding:
    """Bind a raw packet payload to the supported typed packet classes."""
    packet_dict = coerce_packet_dict(packet)
    packet_type = packet_dict.get("type")
    if packet_type == "data_project_create":
        return DataProjectCreatePacketBinding.model_validate(packet_dict)
    if packet_type == "data_account_create":
        return DataAccountCreatePacketBinding.model_validate(packet_dict)
    if packet_type == "request_user_modify":
        return RequestUserModifyPacketBinding.model_validate(packet_dict)
    if packet_type == "request_person_merge":
        return RequestPersonMergePacketBinding.model_validate(packet_dict)
    if packet_type == "request_project_inactivate":
        return RequestProjectInactivatePacketBinding.model_validate(packet_dict)
    if packet_type == "request_account_inactivate":
        return RequestAccountInactivatePacketBinding.model_validate(packet_dict)
    if packet_type == "request_project_reactivate":
        return RequestProjectReactivatePacketBinding.model_validate(packet_dict)
    if packet_type == "request_account_reactivate":
        return RequestAccountReactivatePacketBinding.model_validate(packet_dict)
    if packet_type == "inform_transaction_complete":
        return InformTransactionCompletePacketBinding.model_validate(packet_dict)
    if packet_type == "request_project_create":
        return RequestProjectCreatePacketBinding.model_validate(packet_dict)
    if packet_type == "request_account_create":
        return RequestAccountCreatePacketBinding.model_validate(packet_dict)
    raise UnsupportedPacketType(f"Unsupported packet type: {packet_type!r}")
