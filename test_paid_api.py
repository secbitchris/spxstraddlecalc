#!/usr/bin/env python3
"""
Test script to verify paid Polygon.io subscription with historical SPX data
"""

import asyncio
import os
import logging
from datetime import date, datetime
from spx_calculator import SPXStraddleCalculator
from discord_notifier import DiscordNotifier

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG)

async def test_paid_subscription():
    """Test the paid Polygon.io subscription with historical data"""
    
    # Get API key from environment
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("❌ POLYGON_API_KEY not found in environment")
        return
    
    # Get Redis URL from environment
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    
    print("🚀 Testing Paid Polygon.io Subscription")
    print("=" * 50)
    print(f"🔗 Using Redis: {redis_url}")
    print(f"🔑 API Key: {api_key[:10]}...")
    
    # Initialize calculator
    calculator = SPXStraddleCalculator(api_key, redis_url)
    await calculator.initialize()
    
    # Test with multiple recent trading days
    test_dates = [
        date(2024, 12, 19),  # Thursday
        date(2024, 12, 18),  # Wednesday  
        date(2024, 12, 17),  # Tuesday
        date(2024, 12, 16),  # Monday
        date(2024, 12, 13),  # Friday
    ]
    
    for test_date in test_dates:
        print(f"\n📅 Testing with date: {test_date}")
        
        try:
            # Test: Get SPX price at 9:30 AM
            print(f"📊 Fetching SPX price at 9:30 AM for {test_date}...")
            
            # Let's try to call the Polygon API directly to see what happens
            import pytz
            et_tz = pytz.timezone('US/Eastern')
            target_datetime = et_tz.localize(datetime.combine(test_date, datetime.min.time().replace(hour=9, minute=30)))
            
            print(f"🔍 Calling Polygon API for I:SPX on {target_datetime.strftime('%Y-%m-%d')}")
            
            try:
                aggs = calculator.polygon_client.get_aggs(
                    ticker="I:SPX",
                    multiplier=1,
                    timespan="minute",
                    from_=target_datetime.strftime('%Y-%m-%d'),
                    to=target_datetime.strftime('%Y-%m-%d'),
                    limit=50000
                )
                
                print(f"📈 API Response: {aggs}")
                if hasattr(aggs, 'results') and aggs.results:
                    print(f"📊 Found {len(aggs.results)} data points")
                    for i, bar in enumerate(aggs.results[:5]):  # Show first 5
                        bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                        print(f"   {i+1}. {bar_time}: O={bar.open}, H={bar.high}, L={bar.low}, C={bar.close}")
                else:
                    print("❌ No results in API response")
                    
            except Exception as api_error:
                print(f"❌ Direct API call failed: {api_error}")
                continue
            
            # Now try the calculator method
            spx_price = await calculator.get_spx_price_at_930am(test_date)
            
            if spx_price:
                print(f"✅ SPX price at 9:30 AM: ${spx_price:.2f}")
                
                # If we got a price, try a full calculation
                print(f"🔄 Attempting full calculation...")
                result = await calculator.calculate_spx_straddle_cost(test_date)
                
                if 'error' not in result:
                    print("🎉 SUCCESS! Full calculation worked!")
                    print(f"   SPX Price: ${result.get('spx_price_930am', 'N/A')}")
                    print(f"   ATM Strike: {result.get('atm_strike', 'N/A')}")
                    print(f"   Call Price: ${result.get('call_price_931am', 'N/A')}")
                    print(f"   Put Price: ${result.get('put_price_931am', 'N/A')}")
                    print(f"   Straddle Cost: ${result.get('straddle_cost', 'N/A')}")
                    break  # Success! Exit the loop
                else:
                    print(f"⚠️ Partial success - got SPX price but full calculation failed: {result['error']}")
            else:
                print("❌ Failed to get SPX price")
                
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            continue
            
    await calculator.close()
    print("\n" + "=" * 50)
    print("🏁 Test completed!")

if __name__ == "__main__":
    asyncio.run(test_paid_subscription()) 