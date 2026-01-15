"""
Onboarding API Routes.

Provides a conversational onboarding flow that uses AI to generate
custom monitoring configurations from natural language descriptions.

The flow is:
1. POST /start - Begin with business description
2. POST /continue - Answer clarifying questions (if needed)
3. POST /refine - Iteratively improve the configuration
4. POST /confirm - Finalize and create the client
5. GET /explain - Get reasoning for configuration choices
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from src.api.dependencies import get_supabase
from src.config.config_generator import (
    ConfigGenerator,
    GeneratorResponse,
    OnboardingSession,
    SessionStatus,
    get_config_generator,
)
from src.config.industry_schema import IndustryConfig


router = APIRouter(prefix="/onboard", tags=["Onboarding"])


# =============================================================================
# Request/Response Models
# =============================================================================

class StartOnboardingRequest(BaseModel):
    """Request to start the onboarding process."""
    business_description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Natural language description of the business and what they want to monitor",
        examples=[
            "I run a dog grooming salon in Leeds. We want to track Google reviews and see how we compare to competitors.",
            "I'm a TikTok fitness influencer with 50k followers. I want to track engagement, growth, and compare with similar creators.",
        ],
    )


class ContinueOnboardingRequest(BaseModel):
    """Request to continue onboarding with answers."""
    session_id: str = Field(..., description="Session ID from the start response")
    answers: str = Field(
        ...,
        min_length=5,
        max_length=5000,
        description="Answers to the clarifying questions",
    )


class RefineConfigRequest(BaseModel):
    """Request to refine an existing configuration."""
    session_id: str = Field(..., description="Session ID")
    refinement: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="What to change about the configuration",
        examples=[
            "Also add a field to track average job value",
            "Remove the pricing theme, we don't want to track that",
            "Add Instagram as a data source",
        ],
    )


class ConfirmOnboardingRequest(BaseModel):
    """Request to confirm and create the client."""
    session_id: str = Field(..., description="Session ID")
    business_name: str = Field(..., min_length=1, max_length=200)
    owner_email: EmailStr = Field(..., description="Email for report delivery")
    location: Optional[str] = Field(None, description="Override location from config")
    schedule_frequency: str = Field(
        "weekly",
        pattern="^(daily|weekly|monthly)$",
        description="Report frequency",
    )
    schedule_day: Optional[str] = Field(
        "monday",
        pattern="^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
    )
    schedule_hour: int = Field(9, ge=0, le=23)


class OnboardingResponse(BaseModel):
    """Response from onboarding endpoints."""
    session_id: str
    status: str = Field(
        ...,
        description="needs_more_info, config_ready, confirmed, or error"
    )
    questions: list[str] = Field(
        default_factory=list,
        description="Questions to ask the user (if status is needs_more_info)"
    )
    config_preview: Optional[dict[str, Any]] = Field(
        None,
        description="Preview of the generated configuration (if status is config_ready)"
    )
    reasoning: str = Field(
        "",
        description="AI's explanation of its choices"
    )
    error: Optional[str] = Field(None, description="Error message if status is error")


class ConfirmResponse(BaseModel):
    """Response after confirming onboarding."""
    client_id: str
    config_id: str
    status: str
    business_name: str
    message: str


class ExplainResponse(BaseModel):
    """Response explaining configuration choices."""
    session_id: str
    business_type: str
    reasoning: str
    field_explanations: list[dict[str, str]]
    theme_explanations: list[dict[str, str]]
    source_explanations: list[dict[str, str]]


# =============================================================================
# Helper Functions
# =============================================================================

def config_to_preview(config: IndustryConfig) -> dict[str, Any]:
    """Convert an IndustryConfig to a preview dictionary."""
    return {
        "config_id": config.config_id,
        "config_name": config.config_name,
        "industry_name": config.industry_name,
        "business_type": config.business_type,
        "entity_name": config.entity_name,
        "location": config.location,
        "market_scope": config.market_scope.value,
        "custom_fields": [
            {
                "name": f.name,
                "display_name": f.display_name,
                "description": f.description,
                "data_type": f.data_type.value,
                "is_kpi": f.is_kpi,
            }
            for f in config.custom_fields
        ],
        "data_sources": [
            {
                "source_type": s.source_type.value,
                "display_name": s.display_name,
                "enabled": s.enabled,
            }
            for s in config.data_sources
        ],
        "themes": [
            {
                "name": t.name,
                "display_name": t.display_name,
                "category": t.category,
            }
            for t in config.themes
        ],
        "competitor_tracking": config.competitor_config is not None,
        "report_sections": len(config.report_config.sections),
        "alert_rules": len(config.alert_rules),
    }


async def save_session_to_db(session: OnboardingSession, supabase) -> None:
    """Save an onboarding session to Supabase."""
    session_data = session.to_dict()

    # Check if session exists
    result = supabase.table("onboarding_sessions").select("id").eq(
        "id", session.session_id
    ).execute()

    if result.data:
        # Update existing
        supabase.table("onboarding_sessions").update({
            "conversation_history": session_data["conversation_history"],
            "current_config": session_data["current_config"],
            "status": session_data["status"],
            "questions": session_data["questions"],
            "generation_reasoning": session_data["generation_reasoning"],
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", session.session_id).execute()
    else:
        # Insert new
        supabase.table("onboarding_sessions").insert({
            "id": session.session_id,
            "conversation_history": session_data["conversation_history"],
            "current_config": session_data["current_config"],
            "status": session_data["status"],
            "questions": session_data["questions"],
            "generation_reasoning": session_data["generation_reasoning"],
            "created_at": session_data["created_at"],
            "updated_at": session_data["updated_at"],
        }).execute()


async def load_session_from_db(session_id: str, supabase) -> Optional[dict]:
    """Load a session from Supabase."""
    result = supabase.table("onboarding_sessions").select("*").eq(
        "id", session_id
    ).execute()

    if result.data:
        return result.data[0]
    return None


# =============================================================================
# Routes
# =============================================================================

@router.post(
    "/start",
    response_model=OnboardingResponse,
    status_code=status.HTTP_200_OK,
    summary="Start onboarding",
    description="Begin the onboarding process with a business description",
)
async def start_onboarding(
    request: StartOnboardingRequest,
    supabase=Depends(get_supabase),
) -> OnboardingResponse:
    """
    Start the onboarding process.

    Takes a natural language description of the business and either:
    - Returns clarifying questions if more info is needed
    - Returns a generated configuration if enough info was provided
    """
    generator = get_config_generator()

    try:
        response = await generator.start_onboarding(request.business_description)

        # Save session to database
        session = generator.get_session(response.session_id)
        if session:
            await save_session_to_db(session, supabase)

        return OnboardingResponse(
            session_id=response.session_id,
            status=response.status.value,
            questions=response.questions,
            config_preview=config_to_preview(response.config) if response.config else None,
            reasoning=response.reasoning,
            error=response.error,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start onboarding: {str(e)}",
        )


@router.post(
    "/continue",
    response_model=OnboardingResponse,
    status_code=status.HTTP_200_OK,
    summary="Continue onboarding",
    description="Continue onboarding by answering clarifying questions",
)
async def continue_onboarding(
    request: ContinueOnboardingRequest,
    supabase=Depends(get_supabase),
) -> OnboardingResponse:
    """
    Continue the onboarding process with user answers.

    Takes answers to the clarifying questions and either:
    - Returns more questions if still needed
    - Returns the generated configuration
    """
    generator = get_config_generator()

    # Try to load session from database if not in memory
    session = generator.get_session(request.session_id)
    if not session:
        session_data = await load_session_from_db(request.session_id, supabase)
        if session_data:
            session = generator.load_session(session_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

    try:
        response = await generator.continue_onboarding(
            request.session_id, request.answers
        )

        # Save updated session
        session = generator.get_session(response.session_id)
        if session:
            await save_session_to_db(session, supabase)

        return OnboardingResponse(
            session_id=response.session_id,
            status=response.status.value,
            questions=response.questions,
            config_preview=config_to_preview(response.config) if response.config else None,
            reasoning=response.reasoning,
            error=response.error,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to continue onboarding: {str(e)}",
        )


@router.post(
    "/refine",
    response_model=OnboardingResponse,
    status_code=status.HTTP_200_OK,
    summary="Refine configuration",
    description="Iteratively improve the generated configuration",
)
async def refine_config(
    request: RefineConfigRequest,
    supabase=Depends(get_supabase),
) -> OnboardingResponse:
    """
    Refine an existing configuration.

    Allows users to request changes like:
    - "Also track X"
    - "Remove the Y theme"
    - "Add Instagram as a data source"
    """
    generator = get_config_generator()

    # Load session if needed
    session = generator.get_session(request.session_id)
    if not session:
        session_data = await load_session_from_db(request.session_id, supabase)
        if session_data:
            session = generator.load_session(session_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

    if not session.current_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No configuration to refine. Complete the onboarding first.",
        )

    try:
        response = await generator.refine_config(request.session_id, request.refinement)

        # Save updated session
        session = generator.get_session(response.session_id)
        if session:
            await save_session_to_db(session, supabase)

        return OnboardingResponse(
            session_id=response.session_id,
            status=response.status.value,
            questions=response.questions,
            config_preview=config_to_preview(response.config) if response.config else None,
            reasoning=response.reasoning,
            error=response.error,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refine configuration: {str(e)}",
        )


@router.post(
    "/confirm",
    response_model=ConfirmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm and create client",
    description="Finalize the configuration and create the client",
)
async def confirm_onboarding(
    request: ConfirmOnboardingRequest,
    supabase=Depends(get_supabase),
) -> ConfirmResponse:
    """
    Confirm the onboarding and create the client.

    This finalizes the configuration and creates:
    - A new client in the clients table
    - The industry config in the industry_configs table
    - A scheduled job for report generation
    """
    generator = get_config_generator()

    # Load session
    session = generator.get_session(request.session_id)
    if not session:
        session_data = await load_session_from_db(request.session_id, supabase)
        if session_data:
            session = generator.load_session(session_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

    if not session.current_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No configuration ready. Complete the onboarding first.",
        )

    if session.status != SessionStatus.CONFIG_READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Configuration not ready. Current status: {session.status.value}",
        )

    config = session.current_config

    try:
        # Generate IDs
        client_id = str(uuid4())
        config_id = config.config_id

        # Update config with final details
        config.location = request.location or config.location
        config.updated_at = datetime.utcnow()

        # 1. Create the client
        client_data = {
            "id": client_id,
            "business_name": request.business_name,
            "location": config.location or "",
            "owner_email": request.owner_email,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        supabase.table("clients").insert(client_data).execute()

        # 2. Save the industry config
        config_data = {
            "id": config_id,
            "client_id": client_id,
            "config_data": config.model_dump(mode="json"),
            "source_description": config.source_description,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        supabase.table("industry_configs").insert(config_data).execute()

        # 3. Create the scheduled job
        from src.scheduler.scheduler import calculate_next_run

        next_run = calculate_next_run(
            request.schedule_frequency,
            request.schedule_day,
            request.schedule_hour,
        )

        job_data = {
            "id": str(uuid4()),
            "client_id": client_id,
            "business_name": request.business_name,
            "location": config.location or "",
            "owner_email": request.owner_email,
            "frequency": request.schedule_frequency,
            "schedule_day": request.schedule_day,
            "schedule_hour": request.schedule_hour,
            "is_active": True,
            "next_run": next_run.isoformat() if next_run else None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        supabase.table("scheduled_jobs").insert(job_data).execute()

        # 4. Update session status
        session.status = SessionStatus.CONFIRMED
        await save_session_to_db(session, supabase)

        return ConfirmResponse(
            client_id=client_id,
            config_id=config_id,
            status="active",
            business_name=request.business_name,
            message=f"Successfully created {request.business_name} with custom configuration. "
                    f"Reports will be generated {request.schedule_frequency} at {request.schedule_hour}:00.",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to confirm onboarding: {str(e)}",
        )


@router.get(
    "/{session_id}/explain",
    response_model=ExplainResponse,
    status_code=status.HTTP_200_OK,
    summary="Get configuration explanation",
    description="Get AI's reasoning for the configuration choices",
)
async def explain_config(
    session_id: str,
    supabase=Depends(get_supabase),
) -> ExplainResponse:
    """
    Get a detailed explanation of the configuration choices.

    Returns the AI's reasoning for:
    - Each custom field
    - Each analysis theme
    - Each data source
    """
    generator = get_config_generator()

    # Load session
    session = generator.get_session(session_id)
    if not session:
        session_data = await load_session_from_db(session_id, supabase)
        if session_data:
            session = generator.load_session(session_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

    if not session.current_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No configuration available",
        )

    config = session.current_config

    # Generate explanations
    field_explanations = [
        {
            "name": f.display_name,
            "explanation": f"Tracks {f.description.lower()}. "
                          f"{'This is a key performance indicator.' if f.is_kpi else ''}"
                          f"Data comes from {f.source_type.value} and is displayed as {f.display_format}.",
        }
        for f in config.custom_fields
    ]

    theme_explanations = [
        {
            "name": t.display_name,
            "explanation": f"Analyzes {t.description.lower()} in the '{t.category}' category. "
                          f"Positive signals include: {', '.join(t.positive_indicators[:3])}. "
                          f"Negative signals include: {', '.join(t.negative_indicators[:3])}.",
        }
        for t in config.themes
    ]

    source_explanations = [
        {
            "name": s.display_name,
            "explanation": f"Collects data from {s.source_type.value}. "
                          f"Syncs {s.sync_frequency.value}. "
                          f"{'Requires authentication.' if s.auth_required else 'No authentication required.'}",
        }
        for s in config.data_sources
    ]

    return ExplainResponse(
        session_id=session_id,
        business_type=config.business_type,
        reasoning=config.generation_reasoning,
        field_explanations=field_explanations,
        theme_explanations=theme_explanations,
        source_explanations=source_explanations,
    )


@router.get(
    "/{session_id}",
    response_model=OnboardingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get session status",
    description="Get the current state of an onboarding session",
)
async def get_session_status(
    session_id: str,
    supabase=Depends(get_supabase),
) -> OnboardingResponse:
    """Get the current status of an onboarding session."""
    generator = get_config_generator()

    # Load session
    session = generator.get_session(session_id)
    if not session:
        session_data = await load_session_from_db(session_id, supabase)
        if session_data:
            session = generator.load_session(session_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

    return OnboardingResponse(
        session_id=session.session_id,
        status=session.status.value,
        questions=session.questions,
        config_preview=config_to_preview(session.current_config) if session.current_config else None,
        reasoning=session.generation_reasoning,
        error=session.error_message,
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete session",
    description="Delete an onboarding session",
)
async def delete_session(
    session_id: str,
    supabase=Depends(get_supabase),
) -> None:
    """Delete an onboarding session."""
    # Delete from database
    supabase.table("onboarding_sessions").delete().eq("id", session_id).execute()

    # Remove from memory
    generator = get_config_generator()
    if session_id in generator._sessions:
        del generator._sessions[session_id]
