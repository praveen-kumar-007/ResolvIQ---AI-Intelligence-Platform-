import pytest
from pydantic import ValidationError
from app.models.query_models import (
    AggregationSpec,
    AggregationType,
    AllowedColumn,
    FilterCondition,
    FilterOperator,
    QueryIntent,
    QueryOperation,
    SortOrder,
)
from app.services.query_executor import query_executor
from app.services.llm_service import llm_service


def test_field_whitelisting_rejection():
    """Verify that disallowed columns or SQL injection attempts fail schema validation."""
    with pytest.raises(ValidationError):
        # Disallowed column 'credit_card' or injection
        FilterCondition(
            field="credit_card; DROP TABLE support_tickets;",  # type: ignore
            operator=FilterOperator.EQUALS,
            value="123"
        )


def test_query_open_tickets():
    """Query 1: 'How many tickets are currently open?' -> Exact 111."""
    intent = QueryIntent(
        operation=QueryOperation.COUNT,
        filters=[
            FilterCondition(field=AllowedColumn.STATUS, operator=FilterOperator.EQUALS, value="Open")
        ]
    )
    result = query_executor.execute(intent)
    assert result["operation"] == "count"
    assert result["data"]["count"] == 111


def test_query_critical_unresolved():
    """Query 2: 'How many critical tickets are unresolved?' -> Exact 31."""
    intent = QueryIntent(
        operation=QueryOperation.COUNT,
        filters=[
            FilterCondition(field=AllowedColumn.PRIORITY, operator=FilterOperator.EQUALS, value="Critical"),
            FilterCondition(field=AllowedColumn.STATUS, operator=FilterOperator.NOT_EQUALS, value="Resolved")
        ]
    )
    result = query_executor.execute(intent)
    assert result["data"]["count"] == 31


def test_query_top_resolving_agent():
    """Query 3: 'Which agent resolved the most tickets?' -> AGT-09 & AGT-12 with 37."""
    intent = QueryIntent(
        operation=QueryOperation.GROUP_BY,
        group_by=AllowedColumn.AGENT_ID,
        filters=[
            FilterCondition(field=AllowedColumn.STATUS, operator=FilterOperator.EQUALS, value="Resolved")
        ],
        aggregation=AggregationSpec(function=AggregationType.COUNT, field=AllowedColumn.TICKET_ID),
        order_direction=SortOrder.DESC,
        limit=2
    )
    result = query_executor.execute(intent)
    assert result["operation"] == "group_by"
    top_agent = result["data"][0]
    assert top_agent["agent_id"] in ("AGT-09", "AGT-12")
    assert top_agent["agg_value"] == 37


def test_query_technical_avg_rating():
    """Query 4: 'What is the average customer rating for Technical category tickets?' -> 3.74."""
    intent = QueryIntent(
        operation=QueryOperation.AGGREGATE,
        aggregation=AggregationSpec(function=AggregationType.AVG, field=AllowedColumn.CUSTOMER_RATING),
        filters=[
            FilterCondition(field=AllowedColumn.CATEGORY, operator=FilterOperator.EQUALS, value="Technical")
        ]
    )
    result = query_executor.execute(intent)
    assert result["operation"] == "aggregate"
    assert result["data"]["value"] == 3.74
    assert result["data"]["sample_size"] == 104


def test_query_critical_not_resolved_in_12h():
    """Query 5: Critical tickets taking > 12h resolution time -> 3."""
    intent = QueryIntent(
        operation=QueryOperation.COUNT,
        filters=[
            FilterCondition(field=AllowedColumn.PRIORITY, operator=FilterOperator.EQUALS, value="Critical"),
            FilterCondition(field=AllowedColumn.RESOLUTION_TIME_HRS, operator=FilterOperator.GREATER_THAN, value=12.0)
        ]
    )
    result = query_executor.execute(intent)
    assert result["data"]["count"] == 3


def test_query_category_distribution():
    """Query 6: Category with highest tickets -> General with 189."""
    intent = QueryIntent(
        operation=QueryOperation.GROUP_BY,
        group_by=AllowedColumn.CATEGORY,
        aggregation=AggregationSpec(function=AggregationType.COUNT, field=AllowedColumn.TICKET_ID),
        order_direction=SortOrder.DESC,
        limit=3
    )
    result = query_executor.execute(intent)
    assert result["data"][0]["category"] == "General"
    assert result["data"][0]["agg_value"] == 189


def test_query_longest_resolution_times():
    """Query 8: Top tickets with longest resolution time -> TKT-108 (119.7)."""
    intent = QueryIntent(
        operation=QueryOperation.TOP_N,
        filters=[
            FilterCondition(field=AllowedColumn.RESOLUTION_TIME_HRS, operator=FilterOperator.IS_NOT_NULL)
        ],
        order_by=AllowedColumn.RESOLUTION_TIME_HRS,
        order_direction=SortOrder.DESC,
        limit=5
    )
    result = query_executor.execute(intent)
    assert len(result["data"]) == 5
    assert result["data"][0]["ticket_id"] == "TKT-108"
    assert result["data"][0]["resolution_time_hrs"] == 119.7


def test_ambiguous_query_handling():
    """Verify that ambiguous queries flag is_ambiguous=True with clarification."""
    intent = llm_service._fallback_parse("What happened yesterday?")
    assert intent.is_ambiguous is True
    assert intent.clarification_needed is not None


@pytest.mark.asyncio
async def test_query_service_sql_transparency():
    """Verify that query_service returns sql_executed and query_intent for technical auditing."""
    from app.services.query_service import query_service
    from app.models.schemas import QueryRequest

    res = await query_service.process_question(QueryRequest(question="How many tickets are currently open?"))
    assert res.query_type == "count"
    assert res.result == {"count": 111}
    assert res.sql_executed is not None
    assert "SELECT COUNT(*)" in res.sql_executed
    assert res.query_intent is not None
    assert res.query_intent["operation"] == "count"

