from enum import Enum
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class AllowedColumn(str, Enum):
    TICKET_ID = "ticket_id"
    CREATED_AT = "created_at"
    CATEGORY = "category"
    PRIORITY = "priority"
    STATUS = "status"
    RESPONSE_TIME_HRS = "response_time_hrs"
    RESOLUTION_TIME_HRS = "resolution_time_hrs"
    AGENT_ID = "agent_id"
    CUSTOMER_RATING = "customer_rating"
    ISSUE_SUMMARY = "issue_summary"


class QueryOperation(str, Enum):
    COUNT = "count"
    FILTER_LIST = "filter_list"
    AGGREGATE = "aggregate"
    GROUP_BY = "group_by"
    TOP_N = "top_n"


class AggregationType(str, Enum):
    AVG = "avg"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    COUNT = "count"


class FilterOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    IN = "in"
    LIKE = "like"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class FilterCondition(BaseModel):
    field: AllowedColumn
    operator: FilterOperator
    value: Optional[Union[str, int, float, List[Union[str, int, float]]]] = None

    @field_validator("field", mode="before")
    @classmethod
    def normalize_field(cls, v: Any) -> str:
        if isinstance(v, str):
            mapping = {
                "resp_time_hrs": "response_time_hrs",
                "resol_time_hrs": "resolution_time_hrs",
                "cust_rating": "customer_rating",
                "rating": "customer_rating",
                "agent": "agent_id",
            }
            return mapping.get(v.lower().strip(), v.lower().strip())
        return v


class AggregationSpec(BaseModel):
    function: AggregationType
    field: AllowedColumn

    @field_validator("field", mode="before")
    @classmethod
    def normalize_field(cls, v: Any) -> str:
        if isinstance(v, str):
            mapping = {
                "resp_time_hrs": "response_time_hrs",
                "resol_time_hrs": "resolution_time_hrs",
                "cust_rating": "customer_rating",
                "rating": "customer_rating",
                "agent": "agent_id",
            }
            return mapping.get(v.lower().strip(), v.lower().strip())
        return v


class DateRange(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    period_description: Optional[str] = None


class QueryIntent(BaseModel):
    """Strict schema for LLM-parsed query intent before execution."""
    operation: QueryOperation
    fields: List[AllowedColumn] = Field(default_factory=list)
    filters: List[FilterCondition] = Field(default_factory=list)
    aggregation: Optional[AggregationSpec] = None
    group_by: Optional[AllowedColumn] = None
    order_by: Optional[AllowedColumn] = None
    order_direction: SortOrder = SortOrder.DESC
    limit: Optional[int] = Field(default=None, ge=1, le=500)
    date_range: Optional[DateRange] = None
    is_ambiguous: bool = False
    clarification_needed: Optional[str] = None

    @field_validator("order_direction", mode="before")
    @classmethod
    def normalize_order_dir(cls, v: Any) -> SortOrder:
        if not v:
            return SortOrder.DESC
        if isinstance(v, str) and v.lower().strip() in ("asc", "desc"):
            return SortOrder(v.lower().strip())
        return SortOrder.DESC

    @field_validator("group_by", "order_by", mode="before")
    @classmethod
    def normalize_optional_fields(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        if isinstance(v, str):
            val = v.lower().strip()
            if val in ("count", "agg_value", "total", "value", "records", "frequency"):
                return None
            mapping = {
                "resp_time_hrs": "response_time_hrs",
                "resol_time_hrs": "resolution_time_hrs",
                "cust_rating": "customer_rating",
                "rating": "customer_rating",
                "agent": "agent_id",
            }
            normalized = mapping.get(val, val)
            allowed = {c.value for c in AllowedColumn}
            return normalized if normalized in allowed else None
        return v
