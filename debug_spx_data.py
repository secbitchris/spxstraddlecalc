#!/usr/bin/env python3
"""
Debug script to examine SPX data and timestamps
"""

import os
import pytz
from datetime import date, datetime
from polygon import RESTClient

def debug_spx_data():
    """Debug SPX data timestamps"""
    
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("❌ POLYGON_API_KEY not found")
        return
    
    print(f"🔑 Using API key: {api_key[:10]}...")
    
    client = RESTClient(api_key)
    et_tz = pytz.timezone('US/Eastern')
    
    # Test with December 17, 2024
    test_date = date(2024, 12, 17)
    target_datetime = et_tz.localize(datetime.combine(test_date, datetime.min.time().replace(hour=9, minute=30)))
    
    print(f"🔍 Debugging SPX data for {test_date}")
    print(f"📅 Target 9:30 AM ET: {target_datetime}")
    print(f"📅 Target timestamp (ms): {int(target_datetime.timestamp() * 1000)}")
    
    try:
        print("📡 Making API call to Polygon...")
        aggs = client.get_aggs(
            ticker="I:SPX",
            multiplier=1,
            timespan="minute",
            from_=test_date.strftime('%Y-%m-%d'),
            to=test_date.strftime('%Y-%m-%d'),
            limit=50000
        )
        
        print(f"📊 API Response type: {type(aggs)}")
        print(f"📊 API Response: {aggs}")
        
        if aggs and hasattr(aggs, 'results'):
            print(f"📊 Has results attribute: {hasattr(aggs, 'results')}")
            if aggs.results:
                print(f"✅ Got {len(aggs.results)} data points")
                
                # Show first 10 candles with their times
                print("\n📊 First 10 candles:")
                for i, bar in enumerate(aggs.results[:10]):
                    bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                    print(f"   {i+1}. {bar_time.strftime('%H:%M:%S')} - O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close}")
                    
                    # Check if this is 9:30 AM
                    if bar_time.hour == 9 and bar_time.minute == 30:
                        print(f"   ✅ FOUND 9:30 AM candle! Open price: {bar.open}")
                        
                # Look for any 9:30 candles in the entire dataset
                print(f"\n🔍 Searching all {len(aggs.results)} candles for 9:30 AM...")
                found_930 = False
                for bar in aggs.results:
                    bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                    if bar_time.hour == 9 and bar_time.minute == 30:
                        print(f"✅ Found 9:30 AM candle: {bar_time} - Open: {bar.open}")
                        found_930 = True
                        break
                        
                if not found_930:
                    print("❌ No 9:30 AM candle found in dataset")
                    print("📊 Available times:")
                    unique_times = set()
                    for bar in aggs.results[:20]:  # Show first 20 unique times
                        bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                        time_str = bar_time.strftime('%H:%M')
                        if time_str not in unique_times:
                            unique_times.add(time_str)
                            print(f"   - {time_str}")
            else:
                print("❌ Results list is empty")
        else:
            print("❌ No results attribute or no data received from Polygon")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_spx_data() 