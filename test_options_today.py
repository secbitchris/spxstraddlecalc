#!/usr/bin/env python3
"""
Test script to check if we can get SPX options data for a known trading day
"""

import os
import pytz
from datetime import date, datetime
from polygon import RESTClient

def test_options_access():
    """Test if we can access SPX options data for a known trading day"""
    
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("❌ POLYGON_API_KEY not found")
        return
    
    client = RESTClient(api_key)
    et_tz = pytz.timezone('US/Eastern')
    
    # Test with December 16, 2024 (known trading day)
    test_date = date(2024, 12, 16)
    print(f"🗓️ Testing for date: {test_date}")
    
    # Test SPX index data first
    print(f"\n📊 Testing SPX index data...")
    try:
        spx_aggs = client.list_aggs(
            ticker="I:SPX",
            multiplier=1,
            timespan="minute",
            from_=test_date,
            to=test_date,
            limit=50
        )
        
        spx_bars = list(spx_aggs) if hasattr(spx_aggs, '__iter__') else []
        print(f"✅ SPX data: Got {len(spx_bars)} bars")
        
        if spx_bars:
            first_bar = spx_bars[0]
            bar_time = datetime.fromtimestamp(first_bar.timestamp / 1000, tz=et_tz)
            print(f"   First bar: {bar_time.strftime('%H:%M')} - Open: ${first_bar.open}")
            
            # Find 9:30 AM bar
            spx_930_price = None
            for bar in spx_bars:
                bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                if bar_time.hour == 9 and bar_time.minute == 30:
                    spx_930_price = bar.open
                    print(f"   9:30 AM SPX: ${spx_930_price}")
                    break
            
            if spx_930_price:
                # Calculate ATM strike
                atm_strike = round(spx_930_price / 5) * 5
                print(f"   ATM Strike: ${atm_strike}")
                
                # Test options data
                print(f"\n🎯 Testing SPX options data...")
                
                # Build option tickers for December 16, 2024
                expiry_str = test_date.strftime('%y%m%d')  # YYMMDD format
                strike_formatted = f"{int(atm_strike * 1000):08d}"
                
                call_ticker = f"O:SPX{expiry_str}C{strike_formatted}"
                put_ticker = f"O:SPX{expiry_str}P{strike_formatted}"
                
                print(f"   Call ticker: {call_ticker}")
                print(f"   Put ticker: {put_ticker}")
                
                # Test call options
                try:
                    call_aggs = client.list_aggs(
                        ticker=call_ticker,
                        multiplier=1,
                        timespan="minute",
                        from_=test_date,
                        to=test_date,
                        limit=50
                    )
                    
                    call_bars = list(call_aggs) if hasattr(call_aggs, '__iter__') else []
                    print(f"   📞 Call data: Got {len(call_bars)} bars")
                    
                    if call_bars:
                        # Find 9:31 AM bar
                        for bar in call_bars:
                            bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                            if bar_time.hour == 9 and bar_time.minute == 31:
                                print(f"   📞 9:31 AM Call: ${bar.open}")
                                break
                        else:
                            print(f"   📞 No 9:31 AM call bar found")
                            if call_bars:
                                first_call = call_bars[0]
                                first_time = datetime.fromtimestamp(first_call.timestamp / 1000, tz=et_tz)
                                print(f"   📞 First call bar: {first_time.strftime('%H:%M')} - ${first_call.open}")
                    
                except Exception as e:
                    print(f"   ❌ Call options error: {e}")
                
                # Test put options
                try:
                    put_aggs = client.list_aggs(
                        ticker=put_ticker,
                        multiplier=1,
                        timespan="minute",
                        from_=test_date,
                        to=test_date,
                        limit=50
                    )
                    
                    put_bars = list(put_aggs) if hasattr(put_aggs, '__iter__') else []
                    print(f"   📞 Put data: Got {len(put_bars)} bars")
                    
                    if put_bars:
                        # Find 9:31 AM bar
                        for bar in put_bars:
                            bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                            if bar_time.hour == 9 and bar_time.minute == 31:
                                print(f"   📞 9:31 AM Put: ${bar.open}")
                                break
                        else:
                            print(f"   📞 No 9:31 AM put bar found")
                            if put_bars:
                                first_put = put_bars[0]
                                first_time = datetime.fromtimestamp(first_put.timestamp / 1000, tz=et_tz)
                                print(f"   📞 First put bar: {first_time.strftime('%H:%M')} - ${first_put.open}")
                    
                except Exception as e:
                    print(f"   ❌ Put options error: {e}")
            
    except Exception as e:
        print(f"❌ SPX data error: {e}")

if __name__ == "__main__":
    test_options_access() 