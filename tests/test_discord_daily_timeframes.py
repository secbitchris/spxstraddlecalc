#!/usr/bin/env python3
"""
Test script for Discord daily timeframes notifications (1D-14D)
Shows what the Discord daily momentum analysis would look like
"""

import asyncio
import requests
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from discord_notifier import DiscordNotifier

async def test_discord_daily_timeframes():
    """Test the Discord daily timeframes notification formatting"""
    print("🧪 Testing Discord Daily Timeframes Notification")
    print("=" * 60)
    
    try:
        # Get multi-timeframe statistics
        print("📊 Fetching multi-timeframe statistics...")
        response = requests.get("http://localhost:8000/api/spx-straddle/statistics/multi-timeframe")
        
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            return
        
        multi_stats = response.json()
        timeframes = multi_stats.get('timeframes', {})
        
        # Count daily timeframes
        daily_tfs = [k for k in timeframes.keys() if k.endswith('d') and k.replace('d','').isdigit() and int(k.replace('d','')) <= 14]
        print(f"✅ Got {len(daily_tfs)} daily timeframes")
        
        # Create Discord notifier (without webhook for testing)
        notifier = DiscordNotifier()
        
        # Format the daily message
        print("\n📝 Formatting Discord daily message...")
        payload = notifier.format_daily_timeframe_message(multi_stats)
        
        # Display the formatted message
        print("\n" + "="*60)
        print("📱 DISCORD DAILY ANALYSIS PREVIEW:")
        print("="*60)
        print(payload.get('content', 'Error formatting message'))
        print("="*60)
        
        # Show message length
        content_length = len(payload.get('content', ''))
        print(f"\n📏 Message length: {content_length} characters")
        if content_length > 2000:
            print("⚠️  Message is over Discord's 2000 character limit - will be split")
        else:
            print("✅ Message fits within Discord's character limit")
        
        # Show daily timeframes summary
        print(f"\n📈 Daily Timeframes Summary:")
        for tf in sorted(daily_tfs, key=lambda x: int(x.replace('d',''))):
            tf_data = timeframes[tf]
            data_points = tf_data.get('data_points', 0)
            avg_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
            trend = tf_data.get('trend_analysis', {}).get('direction', 'unknown')
            print(f"• {tf.upper()}: {data_points} pts, ${avg_cost:.2f} avg, {trend} trend")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def test_daily_api_endpoint():
    """Test the API endpoint for daily Discord notifications"""
    print("\n🔗 Testing Daily API Endpoint")
    print("=" * 40)
    
    try:
        response = requests.post("http://localhost:8000/api/discord/notify/daily-timeframes")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ API Response: {result.get('message', 'Success')}")
            return True
        else:
            print(f"❌ API Error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Discord Daily Timeframes Notification Test")
    print("=" * 60)
    
    # Run tests
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Test message formatting
        success1 = loop.run_until_complete(test_discord_daily_timeframes())
        
        # Test API endpoint
        success2 = loop.run_until_complete(test_daily_api_endpoint())
        
        print("\n" + "="*60)
        if success1 and success2:
            print("🎉 All tests passed! Discord daily timeframes notifications are ready!")
            print("\n💡 Usage:")
            print("   • API: POST /api/discord/notify/daily-timeframes")
            print("   • Dashboard: Click '⚡ Send Daily Analysis to Discord'")
            print("   • Provides 1D-14D momentum analysis for short-term trading")
        else:
            print("❌ Some tests failed. Check the output above.")
            
    finally:
        loop.close() 