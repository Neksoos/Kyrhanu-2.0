"""
Shop and monetization router.
Handles purchases, currency packs, and rewarded ads.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from database import get_db
from models import User, ShopPurchase, InventoryItem
from config import settings
from services.analytics import analytics, TrackedEvent
from services.anti_cheat import anti_cheat
from routers.auth import get_current_user
from schemas import BuyItemRequest, PurchasePackRequest

router = APIRouter()


@router.get("/catalog")
async def get_shop_catalog(
    current_user: User = Depends(get_current_user)
):
    """Get available shop items with A/B test pricing."""
    from services.analytics import ab_test_manager
    
    # Get user's A/B test config
    ab_config = await ab_test_manager.get_user_config(current_user.id)
    
    # Apply A/B pricing
    packs = {}
    for key, pack in settings.DEFAULT_CURRENCY_PACKS.items():
        price = pack["price_usd"]
        
        # A/B test: energy pricing
        if key == "starter":
            price = ab_config["config"].get("small_price", 25) / 100  # Convert kleynodu to USD approx
        
        packs[key] = {
            **pack,
            "price_usd": price,
            "kleynodu": pack["kleynodu"],
            "bonus_chervontsi": pack["bonus_chervontsi"]
        }
    
    # Shop items from content
    from content.ethno_content import SHOP_ITEMS
    
    return {
        "currency_packs": packs,
        "items": SHOP_ITEMS,
        "ab_group": ab_config["assignments"]
    }


@router.post("/purchase")
async def purchase_pack(
    payload: PurchasePackRequest,
    request: Request,  # stripe, paypal, crypto
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Initiate purchase (stub for real payment integration).
    In production, this would integrate with Stripe/PayPal/TON.
    """
    if payload.pack_key not in settings.DEFAULT_CURRENCY_PACKS:
        raise HTTPException(status_code=404, detail="Pack not found")
    
    pack = settings.DEFAULT_CURRENCY_PACKS[payload.pack_key]
    
    # Track purchase start
    await analytics.track(TrackedEvent(
        name="purchase_start",
        user_id=current_user.id,
        session_id=None,
        properties={
            "pack": payload.pack_key,
            "value": pack["price_usd"],
            "currency": "USD",
            "method": payload.payment_method
        }
    ))
    
    # Create pending purchase record
    purchase = ShopPurchase(
        user_id=current_user.id,
        pack_key=payload.pack_key,
        kleynodu_amount=pack["kleynodu"],
        price_usd=pack["price_usd"],
        currency="USD",
        status="pending",
        payment_provider=payload.payment_method,
        client_ip=request.client.host if request.client else None
    )
    db.add(purchase)
    await db.commit()
    
    # STUB: In production, redirect to payment provider
    # For MVP, auto-complete for testing
    if settings.ENVIRONMENT == "development":
        # Auto-complete in dev
        purchase.status = "completed"
        purchase.completed_at = datetime.utcnow()
        
        current_user.kleynodu += pack["kleynodu"]
        current_user.chervontsi += pack.get("bonus_chervontsi", 0)
        await db.commit()
        
        await analytics.track(TrackedEvent(
            name="purchase_complete",
            user_id=current_user.id,
            session_id=None,
            properties={
                "pack": payload.pack_key,
                "value": pack["price_usd"],
                "kleynodu": pack["kleynodu"]
            }
        ))
        
        return {
            "success": True,
            "status": "completed",
            "kleynodu_added": pack["kleynodu"],
            "total_kleynodu": current_user.kleynodu
        }
    
    # Production: return payment intent/URL
    return {
        "success": True,
        "status": "pending",
        "purchase_id": purchase.id,
        "payment_url": f"/api/v1/payments/{payment_method}/checkout/{purchase.id}",
        "message": "Redirect to payment provider"
    }


@router.post("/buy-item")
async def buy_shop_item(
    payload: BuyItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Purchase item with kleynodu."""
    from content.ethno_content import SHOP_ITEMS
    
    if payload.item_key not in SHOP_ITEMS:
        raise HTTPException(status_code=404, detail="Item not found")
    
    item = SHOP_ITEMS[payload.item_key]
    cost = item["kleynodu_cost"]
    
    if current_user.kleynodu < cost:
        raise HTTPException(status_code=402, detail="Insufficient kleynodu")
    
    # Deduct
    current_user.kleynodu -= cost
    
    # Apply effect
    effect = item["effect"]
    if "energy" in effect:
        current_user.energy = min(
            current_user.max_energy,
            current_user.energy + effect["energy"]
        )
    elif "unlimited_energy_minutes" in effect:
        # Store buff in Redis
        from redis_client import get_redis
        await get_redis().setex(
            f"buff:unlimited_energy:{current_user.id}",
            effect["unlimited_energy_minutes"] * 60,
            "1"
        )
    
    # Add to inventory if applicable
    if "inventory_key" in item:
        inv_item = InventoryItem(
            user_id=current_user.id,
            item_type="consumable",
            item_key=item["inventory_key"],
            acquired_from="shop"
        )
        db.add(inv_item)
    
    await db.commit()
    
    return {
        "success": True,
        "item": item["name"],
        "effect_applied": effect,
        "kleynodu_remaining": current_user.kleynodu
    }


@router.post("/watch-ad")
async def watch_ad_reward(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reward for watching ad."""
    from redis_client import get_redis
    
    redis = get_redis()
    
    # Check daily cap
    today = datetime.utcnow().strftime("%Y-%m-%d")
    ad_key = f"ads:watched:{current_user.id}:{today}"
    watched = int(await redis.get(ad_key) or 0)
    
    if watched >= settings.MAX_ADS_PER_DAY:
        raise HTTPException(status_code=429, detail="Daily ad limit reached")
    
    # Check cooldown
    last_ad = await redis.get(f"ads:last:{current_user.id}")
    if last_ad:
        last_time = datetime.fromisoformat(last_ad)
        cooldown = timedelta(minutes=settings.REWARDED_AD_COOLDOWN_MINUTES)
        if datetime.utcnow() - last_time < cooldown:
            remaining = cooldown - (datetime.utcnow() - last_time)
            raise HTTPException(
                status_code=429,
                detail=f"Ad cooldown: {remaining.seconds}s remaining"
            )
    
    # Grant reward
    current_user.kleynodu += settings.AD_REWARD_KLEYNODU
    current_user.chervontsi += settings.AD_REWARD_CHERVONTSI
    
    # Track
    await redis.incr(ad_key)
    await redis.expire(ad_key, 86400)  # 24h
    await redis.set(f"ads:last:{current_user.id}", datetime.utcnow().isoformat())
    
    await db.commit()
    
    await analytics.track(TrackedEvent(
        name="ad_watched",
        user_id=current_user.id,
        session_id=None,
        properties={
            "reward_kleynodu": settings.AD_REWARD_KLEYNODU,
            "daily_count": watched + 1
        }
    ))
    
    return {
        "success": True,
        "kleynodu_reward": settings.AD_REWARD_KLEYNODU,
        "chervontsi_reward": settings.AD_REWARD_CHERVONTSI,
        "ads_watched_today": watched + 1,
        "max_ads_per_day": settings.MAX_ADS_PER_DAY
    }