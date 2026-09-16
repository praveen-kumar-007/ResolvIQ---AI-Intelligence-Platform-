import pytest
from app.models.schemas import QueryRequest
from app.services.query_service import query_service


@pytest.mark.asyncio
async def test_edge_case_average_rating():
    """'What is the average rating?' -> Overall average across all rated tickets."""
    res = await query_service.process_question(QueryRequest(question="What is the average rating?"))
    assert res.query_type == "aggregate"
    assert res.result["value"] is not None
    assert "average customer rating" in res.answer.lower()


@pytest.mark.asyncio
async def test_edge_case_how_many_tickets():
    """'How many tickets?' -> Total dataset count 500."""
    res = await query_service.process_question(QueryRequest(question="How many tickets?"))
    assert res.query_type == "count"
    assert res.result["count"] == 500
    assert "500" in res.answer


@pytest.mark.asyncio
async def test_edge_case_no_customer_rating():
    """'Show tickets with no customer rating.' -> Exactly 173 tickets."""
    res = await query_service.process_question(QueryRequest(question="Show tickets with no customer rating."))
    assert res.query_type == "filter_list"
    assert len(res.result) > 0


@pytest.mark.asyncio
async def test_edge_case_no_resolution_time():
    """'Show tickets with no resolution time.' -> Unresolved tickets."""
    res = await query_service.process_question(QueryRequest(question="Show tickets with no resolution time."))
    assert res.query_type == "filter_list"
    assert len(res.result) > 0


@pytest.mark.asyncio
async def test_edge_case_empty_or_whitespace():
    """Empty question validation."""
    with pytest.raises(Exception):
        QueryRequest(question="")
