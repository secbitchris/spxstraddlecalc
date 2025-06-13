#!/usr/bin/env python3
"""
Test script for Discord multi-timeframe notifications
Shows what the Discord message would look like with your 500+ days of data
"""

import asyncio
import requests
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from discord_notifier import DiscordNotifier

async def test_discord_multi_timeframe():
    """Test the Discord multi-timeframe notification formatting"""
    print("🧪 Testing Discord Multi-Timeframe Notification")
    print("=" * 60)
    
    try:
        # Get multi-timeframe statistics
        print("📊 Fetching multi-timeframe statistics...")
        response = requests.get("http://localhost:8000/api/spx-straddle/statistics/multi-timeframe")
        
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            return
        
        multi_stats = response.json()
        print(f"✅ Got statistics for {len(multi_stats.get('timeframes', {}))} timeframes")
        
        # Create Discord notifier (without webhook for testing)
        notifier = DiscordNotifier()
        
        # Format the message
        print("\n📝 Formatting Discord message...")
        payload = notifier.format_multi_timeframe_message(multi_stats)
        
        # Display the formatted message
        print("\n" + "="*60)
        print("📱 DISCORD MESSAGE PREVIEW:")
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
        
        # Show key statistics
        timeframes = multi_stats.get('timeframes', {})
        summary = multi_stats.get('summary', {})
        
        print(f"\n📈 Data Summary:")
        print(f"• Total timeframes: {len(timeframes)}")
        print(f"• Max data points: {summary.get('data_coverage', {}).get('900d', {}).get('data_points', 0)}")
        print(f"• Recommended timeframe: {summary.get('recommended_timeframe', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def test_api_endpoint():
    """Test the API endpoint for Discord notifications"""
    print("\n🔗 Testing API Endpoint")
    print("=" * 40)
    
    try:
        response = requests.post("http://localhost:8000/api/discord/notify/multi-timeframe")
        
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
    print("🚀 Discord Multi-Timeframe Notification Test")
    print("=" * 60)
    
    # Run tests
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Test message formatting
        success1 = loop.run_until_complete(test_discord_multi_timeframe())
        
        # Test API endpoint
        success2 = loop.run_until_complete(test_api_endpoint())
        
        print("\n" + "="*60)
        if success1 and success2:
            print("🎉 All tests passed! Discord multi-timeframe notifications are ready!")
            print("\n💡 To enable Discord notifications:")
            print("   1. Set DISCORD_ENABLED=true in your .env file")
            print("   2. Set DISCORD_WEBHOOK_URL=your_webhook_url in your .env file")
            print("   3. Use the API endpoint or dashboard link to send notifications")
        else:
            print("❌ Some tests failed. Check the output above.")
            
    finally:
        loop.close() 