"""
Billing API Routes.

Provides Stripe Checkout integration for subscription payments.

Endpoints:
- POST /billing/create-checkout  Create a Stripe Checkout Session
- POST /billing/webhook          Handle Stripe webhook events
- GET  /billing/success          Checkout success page
- GET  /billing/cancel           Checkout cancellation page
"""

import json

import stripe
import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, EmailStr, Field

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)

_templates = Environment(
    loader=FileSystemLoader("src/templates"),
    autoescape=select_autoescape(["html"]),
)

router = APIRouter(prefix="/billing", tags=["Billing"])


# =============================================================================
# Request / Response Models
# =============================================================================


class CreateCheckoutRequest(BaseModel):
    """Request to create a Stripe Checkout Session."""

    customer_email: EmailStr = Field(
        ...,
        description="Customer email for the Stripe session",
        json_schema_extra={"example": "owner@mybusiness.com"},
    )
    business_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the business subscribing",
        json_schema_extra={"example": "The Corner Cafe"},
    )


class CreateCheckoutResponse(BaseModel):
    """Response containing the Stripe Checkout URL."""

    checkout_url: str = Field(
        ..., description="URL to redirect the customer to Stripe Checkout"
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/create-checkout",
    response_model=CreateCheckoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Create checkout session",
    description="Create a Stripe Checkout Session for a new subscription",
)
async def create_checkout(
    request: CreateCheckoutRequest,
    http_request: Request,
) -> CreateCheckoutResponse:
    """Create a Stripe Checkout Session in subscription mode.

    Returns a checkout_url that the client should redirect the customer to.
    """
    settings = get_settings()

    if not settings.stripe_secret_key:
        logger.error("stripe_secret_key_not_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system not configured",
        )

    if not settings.stripe_price_id:
        logger.error("stripe_price_id_not_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment system not configured",
        )

    stripe.api_key = settings.stripe_secret_key.get_secret_value()

    base = str(http_request.base_url).rstrip("/")
    success_url = f"{base}/api/v1/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base}/api/v1/billing/cancel"

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            customer_email=request.customer_email,
            line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "business_name": request.business_name,
                "customer_email": request.customer_email,
            },
        )

        logger.info(
            "checkout_session_created",
            session_id=session.id,
            customer_email=request.customer_email,
            business_name=request.business_name,
        )

        return CreateCheckoutResponse(checkout_url=session.url)

    except stripe.StripeError as e:
        logger.error("stripe_checkout_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment provider error: {e}",
        )


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook handler",
    description="Receives and processes Stripe webhook events",
    include_in_schema=False,
)
async def stripe_webhook(http_request: Request) -> dict:
    """Handle incoming Stripe webhook events.

    Verifies the webhook signature when STRIPE_WEBHOOK_SECRET is configured,
    then logs supported event types. Database persistence will be added later.
    """
    settings = get_settings()
    payload = await http_request.body()
    sig_header = http_request.headers.get("stripe-signature", "")

    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=settings.stripe_webhook_secret.get_secret_value(),
            )
        except ValueError:
            logger.warning("stripe_webhook_invalid_payload")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payload",
            )
        except stripe.SignatureVerificationError:
            logger.warning("stripe_webhook_invalid_signature")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature",
            )
    else:
        # No secret configured - parse without verification (dev only)
        event = stripe.Event.construct_from(json.loads(payload), stripe.api_key or "")
        logger.warning("stripe_webhook_no_signature_verification")

    event_type = event["type"]

    if event_type == "checkout.session.completed":
        session_data = event["data"]["object"]
        logger.info(
            "stripe_checkout_completed",
            session_id=session_data.get("id"),
            customer_email=session_data.get("customer_email"),
            subscription_id=session_data.get("subscription"),
            business_name=session_data.get("metadata", {}).get("business_name"),
        )
        # TODO: Activate subscription in database

    elif event_type == "customer.subscription.deleted":
        subscription_data = event["data"]["object"]
        logger.info(
            "stripe_subscription_deleted",
            subscription_id=subscription_data.get("id"),
            customer_id=subscription_data.get("customer"),
        )
        # TODO: Deactivate subscription in database

    else:
        logger.debug("stripe_webhook_unhandled_event", event_type=event_type)

    return {"status": "ok"}



@router.get(
    "/session-info",
    status_code=status.HTTP_200_OK,
    summary="Get checkout session info",
    include_in_schema=False,
)
async def get_session_info(session_id: str = "") -> dict:
    """Return business name and email from a Stripe Checkout session."""
    settings = get_settings()
    if not session_id or not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session ID")
    stripe.api_key = settings.stripe_secret_key.get_secret_value()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return {
            "customer_email": session.customer_email or "",
            "business_name": (session.metadata or {}).get("business_name", ""),
        }
    except stripe.StripeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)[:100])


@router.get(
    "/success",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="Checkout success page",
    include_in_schema=False,
)
async def checkout_success(session_id: str = "") -> HTMLResponse:
    """Render the checkout success thank-you page."""
    template = _templates.get_template("onboarding.html")
    html = template.render(session_id=session_id)
    return HTMLResponse(content=html)


@router.get(
    "/cancel",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="Checkout cancelled page",
    include_in_schema=False,
)
async def checkout_cancel() -> HTMLResponse:
    """Render the checkout cancellation page."""
    template = _templates.get_template("checkout_cancel.html")
    html = template.render()
    return HTMLResponse(content=html)
