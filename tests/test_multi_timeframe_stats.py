#!/usr/bin/env python3
"""
Test script for multi-timeframe statistics functionality
"""

import requests
import json
import sys

def test_multi_timeframe_endpoint():
    """Test the multi-timeframe statistics endpoint"""
    print("🧪 Testing Multi-Timeframe Statistics Endpoint...")
    
    try:
        # Test the endpoint
        response = requests.get("http://localhost:8000/api/spx-straddle/statistics/multi-timeframe")
        
        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        data = response.json()
        
        # Check response structure
        if data.get('status') != 'success':
            print(f"❌ API Error: {data.get('message', 'Unknown error')}")
            return False
        
        timeframes = data.get('timeframes', {})
        summary = data.get('summary', {})
        
        print(f"✅ Status: {data['status']}")
        print(f"✅ Available timeframes: {len(timeframes)}")
        print(f"✅ Recommended timeframe: {summary.get('recommended_timeframe', 'N/A')}")
        print(f"✅ Trend consistency: {'Consistent' if summary.get('trend_consistency') else 'Mixed'}")
        
        # Check expected timeframes
        expected_periods = [30, 45, 60, 90, 120, 180, 240, 360, 540, 720, 900]
        found_periods = [tf['period_days'] for tf in timeframes.values()]
        
        print(f"\n📊 Timeframe Analysis:")
        for period in expected_periods:
            period_key = f"{period}d"
            if period_key in timeframes:
                tf_data = timeframes[period_key]
                data_points = tf_data['data_points']
                coverage = summary.get('data_coverage', {}).get(period_key, {}).get('coverage_percentage', 0)
                trend = tf_data.get('trend_analysis', {}).get('direction', 'unknown')
                avg_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
                
                print(f"  {period:3d}d: {data_points:3d} points ({coverage:5.1f}% coverage) - {trend:>10s} trend - ${avg_cost:.2f} avg")
            else:
                print(f"  {period:3d}d: ❌ Insufficient data")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Server not running on port 8000")
        print("💡 Try: source venv/bin/activate && python -c \"import uvicorn; from api_server import app; uvicorn.run(app, host='0.0.0.0', port=8000)\" &")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_dashboard_integration():
    """Test that the dashboard shows multi-timeframe statistics"""
    print("\n🧪 Testing Dashboard Integration...")
    
    try:
        response = requests.get("http://localhost:8000/api/spx-straddle/dashboard")
        
        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
        
        html_content = response.text
        
        # Check for multi-timeframe content
        if "Multi-Timeframe Statistics" in html_content:
            print("✅ Dashboard shows Multi-Timeframe Statistics section")
        else:
            print("❌ Dashboard missing Multi-Timeframe Statistics section")
            return False
        
        if "Available Timeframes:" in html_content:
            print("✅ Dashboard shows timeframe summary")
        else:
            print("❌ Dashboard missing timeframe summary")
            return False
        
        if "View Full Multi-Timeframe Data" in html_content:
            print("✅ Dashboard has link to full multi-timeframe data")
        else:
            print("❌ Dashboard missing link to full data")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Dashboard test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Multi-Timeframe Statistics Test Suite")
    print("=" * 50)
    
    success = True
    
    # Test API endpoint
    if not test_multi_timeframe_endpoint():
        success = False
    
    # Test dashboard integration
    if not test_dashboard_integration():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 All tests passed! Multi-timeframe statistics are working correctly.")
    else:
        print("❌ Some tests failed. Check the output above for details.")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 