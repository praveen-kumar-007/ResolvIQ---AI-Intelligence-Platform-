import pytest
from app.models.schemas import QueryRequest
from app.services.query_service import query_service


@pytest.mark.asyncio
async def test_sample_query_1_open_tickets():
    """Sample Query 1: 'How many tickets are currently open?' -> Exact 111 tickets."""
    req = QueryRequest(question="How many tickets are currently open?")
    res = await query_service.process_question(req)

    assert res.query_type == "count"
    assert res.result["count"] == 111
    assert "111" in res.answer
    assert res.is_ambiguous is False


@pytest.mark.asyncio
async def test_sample_query_2_top_agent():
    """Sample Query 2: 'Which agent resolved the most tickets this month?' -> AGT-12 / AGT-09 with 37."""
    req = QueryRequest(question="Which agent resolved the most tickets this month?")
    res = await query_service.process_question(req)

    assert res.query_type == "group_by"
    assert isinstance(res.result, list)
    assert len(res.result) > 0
    top_agent = res.result[0]
    assert top_agent["agent_id"] in ("AGT-12", "AGT-09")
    assert top_agent["agg_value"] == 37
    assert res.is_ambiguous is False


@pytest.mark.asyncio
async def test_sample_query_3_critical_unresolved_12h():
    """Sample Query 3: 'Show me all Critical tickets not resolved within 12 hours.' -> 3 tickets."""
    req = QueryRequest(question="Show me all Critical tickets not resolved within 12 hours.")
    res = await query_service.process_question(req)

    assert res.query_type in ("filter_list", "top_n")
    assert isinstance(res.result, list)
    assert len(res.result) == 3
    for ticket in res.result:
        assert ticket["priority"] == "Critical"
        assert ticket["resolution_time_hrs"] > 12.0
    assert "Found 3 tickets" in res.answer


@pytest.mark.asyncio
async def test_sample_query_4_technical_avg_rating():
    """Sample Query 4: 'What is the average customer rating for Technical category tickets?' -> 3.74."""
    req = QueryRequest(question="What is the average customer rating for Technical category tickets?")
    res = await query_service.process_question(req)

    assert res.query_type == "aggregate"
    assert res.result["metric"] == "avg"
    assert res.result["value"] == 3.74
    assert res.result["sample_size"] == 104
    assert "3.74" in res.answer


@pytest.mark.asyncio
async def test_sample_query_5_resolution_anomalies():
    """Sample Query 5: 'Are there any anomalies in resolution times this week?' -> 21 tickets."""
    req = QueryRequest(question="Are there any anomalies in resolution times this week?")
    res = await query_service.process_question(req)

    assert res.query_type in ("filter_list", "top_n")
    assert isinstance(res.result, list)
    assert len(res.result) == 21
    for ticket in res.result:
        assert ticket["resolution_time_hrs"] > 48.35
    assert "21" in res.answer
